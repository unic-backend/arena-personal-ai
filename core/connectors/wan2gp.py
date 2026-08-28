"""Connecteur WanGP (Wan2GP) — generer une video sur sa propre carte graphique.

WanGP est un generateur video local, concu pour les petites cartes : il annonce
tourner des 6 Go de VRAM, et le proprietaire en a 12. Rien ne sort de chez lui,
ce qui est la regle de ce projet (DEC-0002).

**Comment ARENA lui parle.** WanGP n'a pas d'API HTTP : son interface est
Gradio. Mais il embarque un **serveur MCP** — un protocole typé — et c'est par
la qu'ARENA passe. Le format de file d'attente `--process` a ete ecarte : sa
structure interne n'est pas documentee, et la deviner aurait ete exactement
l'erreur deja commise une fois sur un protocole.

Pour que ce connecteur devienne operationnel, le proprietaire lance chez lui :

    python wgp.py --mcp --mcp-transport streamable-http --mcp-host 127.0.0.1 --mcp-port 8765

Tant que cette commande n'a pas tourne, la sonde rapporte `NON_CONFIGURE` avec
ce qui manque. Elle ne suppose pas, elle demande.

**Quatre regles :**

1. **La sonde interroge le serveur.** Elle demande la liste des outils et
   verifie que la generation y est. Un port ouvert ne prouve rien.

2. **Generer est une ecriture, et elle passe par une confirmation.** Une
   generation monopolise la carte graphique plusieurs minutes. Elle ne part pas
   parce qu'une phrase y ressemblait.

3. **La generation ne se fait pas attendre ici.** `wangp_generate` rend un
   identifiant de tache ; c'est lui la preuve du succes, et c'est la file de
   travaux de fond (`core/execution/travaux.py`) qui patiente. Le chat n'attend
   jamais une video.

4. **Le texte qui revient de WanGP est une donnee.** Il traverse la frontiere de
   confiance avant d'approcher une invite, au meme titre qu'une page web.
"""
import logging
import os
from typing import Any, Dict, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.mcp.transport import ClientMcp

logger = logging.getLogger("usman.connecteurs.wan2gp")

#: Ou joindre le serveur MCP de WanGP. Dans l'environnement, jamais en dur.
WAN2GP_URL = os.getenv("WAN2GP_MCP_URL", "http://127.0.0.1:8765")
WAN2GP_CHEMIN = os.getenv("WAN2GP_MCP_PATH", "/mcp")

#: Ce qu'il manque, dit une seule fois : le message, la sante et la
#: documentation ne peuvent pas diverger.
CE_QUI_MANQUE = (
    "WanGP demarre avec son serveur MCP : "
    "python wgp.py --mcp --mcp-transport streamable-http "
    "--mcp-host 127.0.0.1 --mcp-port 8765"
)

#: L'outil sans lequel ce connecteur n'a pas de raison d'exister.
OUTIL_GENERER = "wangp_generate"

#: Plafond que **nous** nous imposons, pas un quota publie par WanGP : une
#: generation occupe la carte graphique plusieurs minutes, et en empiler dix
#: parce qu'une boucle s'est emballee couterait une soiree de calcul.
GENERATIONS_PAR_MINUTE = 4


class Wan2GPConnector(Connecteur):
    """Generation video locale, pilotee par MCP."""

    service = "video_generation"
    nom = "wan2gp"

    #: Capacite -> outil MCP, et les parametres qu'elle transmet. Un parametre
    #: absent de cette table n'est jamais envoye : l'appelant ne choisit pas
    #: l'appel, il choisit une capacite declaree.
    ROUTES: Dict[str, Any] = {
        "modeles": ("wangp_models", ("query", "limit")),
        "generer": (OUTIL_GENERER, ("source", "wait", "timeout_s")),
        "etat_travail": ("wangp_get_job", ("job_id", "event_limit")),
        "annuler_travail": ("wangp_cancel_job", ("job_id",)),
        "galerie": ("wangp_list_gallery", ("media_type", "limit")),
    }

    def __init__(self, client: Optional[ClientMcp] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.client = client or ClientMcp(WAN2GP_URL, WAN2GP_CHEMIN)

    def capacites(self) -> Dict[str, Capacite]:
        """Cinq capacites. Une seule ecrit, et c'est la plus chere."""
        return {
            "modeles": Capacite(
                nom="modeles", action="read",
                description="Liste les modeles video installes dans WanGP.",
                ecriture=False),
            "generer": Capacite(
                nom="generer", action="generate",
                description="Lance une generation video sur la carte graphique locale.",
                ecriture=True, quota_par_minute=GENERATIONS_PAR_MINUTE),
            "etat_travail": Capacite(
                nom="etat_travail", action="read",
                description="Ou en est une generation lancee, par son identifiant.",
                ecriture=False),
            "annuler_travail": Capacite(
                nom="annuler_travail", action="cancel",
                description="Arrete une generation en cours.",
                ecriture=True),
            "galerie": Capacite(
                nom="galerie", action="read",
                description="Les videos et images deja produites par WanGP.",
                ecriture=False),
        }

    def sonder(self) -> Sante:
        """Demande la liste des outils. Un port ouvert ne prouve rien."""
        from core.connectors.base import _maintenant

        reponse = self.client.outils()
        if not reponse.ok:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"WanGP ne repond pas sur {self.client.url} ({reponse.raison}).",
                ce_qui_manque=CE_QUI_MANQUE,
                mesure_le=_maintenant(),
            )

        noms = {str((outil or {}).get("name") or "")
                for outil in (reponse.resultat.get("tools") or [])}
        if OUTIL_GENERER not in noms:
            return Sante(
                etat=EtatSante.EN_PANNE,
                message=(f"WanGP repond mais n'annonce pas {OUTIL_GENERER} "
                         f"({len(noms)} outil(s) vus)."),
                mesure_le=_maintenant(),
            )
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message=f"WanGP repond : {len(noms)} outil(s), generation disponible.",
            mesure_le=_maintenant(),
        )

    def authentifier(self) -> bool:
        """Vrai : le serveur est local et ne demande aucun identifiant.

        Ce n'est pas une authentification reussie, c'est l'absence
        d'authentification requise — et c'est ce qui rend ce connecteur
        utilisable sans toucher au moindre secret.
        """
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        """Appelle l'outil MCP correspondant et rend son resultat avec sa preuve."""
        outil, acceptes = self.ROUTES[capacite.nom]
        arguments = {cle: valeur for cle, valeur in parametres.items()
                     if cle in acceptes and valeur is not None}

        if capacite.nom == "generer" and not arguments.get("source"):
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucune description de video : rien a generer.")

        reponse = self.client.appeler(outil, arguments)
        if not reponse.ok:
            if "Connect" in reponse.raison or "HTTP 4" in reponse.raison:
                return non_configure(action=capacite.nom, cible=self.nom,
                                     ce_qui_manque=CE_QUI_MANQUE, detail_erreur=reponse.raison)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"WanGP a refuse l'appel : {reponse.raison}.", outil=outil)

        donnees = reponse.donnees()
        identifiant = self._identifiant_de_tache(donnees)

        if capacite.nom == "generer" and not identifiant:
            # Sans identifiant, rien ne permettra de suivre la generation ni de
            # prouver qu'elle a eu lieu. Un succes sans preuve ne se construit pas.
            return echec(action=capacite.nom, cible=self.nom,
                         message="WanGP a accepte l'appel sans rendre d'identifiant de tache.",
                         outil=outil)

        return succes(
            action=capacite.nom, cible=self.nom,
            message=self._resume(capacite.nom, identifiant),
            preuve=identifiant or f"{outil} a repondu",
            donnees=donnees,
            outil=outil,
        )

    @staticmethod
    def _identifiant_de_tache(donnees: Any) -> str:
        """L'identifiant rendu par WanGP, quel que soit le nom qu'il lui donne."""
        if not isinstance(donnees, dict):
            return ""
        for cle in ("job_id", "id", "task_id"):
            valeur = donnees.get(cle)
            if valeur:
                return str(valeur)
        return ""

    @staticmethod
    def _resume(nom: str, identifiant: str) -> str:
        if nom == "generer":
            return (f"Generation lancee sur la carte graphique locale (tache {identifiant}). "
                    "Elle avance en fond ; le chat ne l'attend pas.")
        return f"WanGP a repondu pour {nom}."
