"""Connecteur Drift — appelle son serveur MCP intégré, jamais son code importé.

**Licence, vérifiée avant d'écrire une ligne** (mission « Drift dans le
workspace Video », 06/09/2026) : Drift (CutWire-Studios/Drift) et
Drift-Addons sont tous deux sous GNU GPLv3 (fichiers `LICENSE` des deux
dépôts, lus directement — pas un paraphrase de README). GPLv3 copyleft fort :
même frontière déjà tenue pour VoiceStudio (AGPL) et KrillinAI (GPL-3.0,
DEC-0049) — un programme SÉPARÉ, installé à côté de ce dépôt, jamais importé
ni copié. Ce que ce connecteur appelle n'est pas du code Drift : c'est son
**propre serveur MCP documenté** (`docs/MCP.md` du dépôt Drift), exactement
la frontière qu'il propose lui-même à un agent externe — Drift n'entre donc
JAMAIS dans ce dépôt, ARENA reste un client HTTP de son protocole.

**Le protocole, tel que documenté par Drift lui-même** : `POST /mcp` avec
`Authorization: Bearer <jeton>` (le serveur ne répond que sur `127.0.0.1`,
mais exige quand même ce jeton — généré par session dans Drift, jamais fixe).
Cinq opérations exposées comme des outils MCP : `catalog` (liste les dix
« toolboxes » — media/timeline/canvas/playback/text/effects/subtitles/audio/
ai/scene), `toolbox({name})` (le schéma JSON réel d'UNE toolbox, récupéré EN
DIRECT — jamais deviné ici : une opération Drift n'est validée que si elle
apparaît dans ce schéma, voir `core/montage/planificateur_drift.py`),
`apply({ops:[...]})` (exécute une liste de mutations comme un seul geste
d'annulation), `inspect({clips,detail})` (état complet du projet/clips/
effets), `capture()` (une image fixe JPEG de la composition).

**Portée de ce connecteur, volontairement étroite** (mission : « DRIFT
APPARTIENT EXCLUSIVEMENT AU WORKSPACE VIDEO ») : ses cinq capacités ne sont
déclarées nulle part ailleurs que dans `core/production/plan_video.py`
(`CAPACITES_VIDEO`) et `agents/video/production_agent.py`. Rien dans
`agents/plaquiste/`, `core/production/ifc*.py` ou tout chemin métier
UniC Plaquiste ne référence ce module — un test le vérifie
(`tests/core/test_connecteur_drift.py::TestFrontiereWorkspaceVideo`).

**Quatre règles, mêmes que WanGP (`core/connectors/wan2gp.py`) :**

1. **La sonde interroge le serveur.** Elle demande la liste des outils et
   vérifie que `apply` y est. Un port ouvert ne prouve rien.
2. **`apply` est une écriture, et elle passe par confirmation.** Elle
   modifie un projet réel dans Drift — jamais déclenchée parce qu'une
   phrase y ressemblait.
3. **Aucune URL ni jeton par défaut** (DEC-0002) : `DRIFT_MCP_URL` et
   `DRIFT_MCP_TOKEN` sont lus à l'appel (jamais au chargement du module,
   pour que les tests les fixent), et leur absence rapporte
   `NON_CONFIGURE` — jamais un port deviné, contrairement à WanGP dont le
   port par défaut (8765) est documenté dans son propre README. Celui de
   Drift ne l'est pas : rien n'est supposé.
4. **Le texte qui revient de Drift est une donnée.** Il traverse la
   frontière de confiance avant d'approcher une invite, au même titre
   qu'une page web ou une transcription.
"""
import logging
import os
from typing import Any, Dict, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.mcp.transport import ClientMcp

logger = logging.getLogger("usman.connecteurs.drift")


def _base_url() -> str:
    return os.getenv("DRIFT_MCP_URL", "").strip().rstrip("/")


def _jeton() -> str:
    return os.getenv("DRIFT_MCP_TOKEN", "").strip()


CE_QUI_MANQUE = (
    "Drift n'est pas configuré : ouvrir Drift, Réglages -> Agent access, "
    "l'activer, puis DRIFT_MCP_URL=http://127.0.0.1:<port> et "
    "DRIFT_MCP_TOKEN=<jeton affiché> dans .env."
)

#: L'outil sans lequel ce connecteur n'a pas de raison d'exister.
OUTIL_APPLIQUER = "apply"

#: Capacité -> (outil MCP, parametres transmis). Cinq capacités seulement :
#: les cinq operations que Drift documente lui-meme dans `docs/MCP.md`.
ROUTES: Dict[str, Any] = {
    "catalogue": ("catalog", ()),
    "boite_a_outils": ("toolbox", ("name",)),
    "etat_projet": ("inspect", ("clips", "detail")),
    "capture": ("capture", ()),
    "appliquer": (OUTIL_APPLIQUER, ("ops",)),
}


class ConnecteurDrift(Connecteur):
    """Éditeur vidéo Drift, piloté par son propre serveur MCP."""

    service = "video_drift"
    nom = "drift"

    def __init__(self, client: Optional[ClientMcp] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client_impose = client

    def _client(self) -> Optional[ClientMcp]:
        """Construit le client au moment de l'appel : l'URL/le jeton peuvent
        changer entre deux appels (tests, ou Drift redémarré avec un nouveau
        jeton de session)."""
        if self._client_impose is not None:
            return self._client_impose
        base_url, jeton = _base_url(), _jeton()
        if not base_url or not jeton:
            return None
        return ClientMcp(base_url, "/mcp", jeton=jeton)

    def capacites(self) -> Dict[str, Capacite]:
        """Cinq capacités. Une seule écrit, et c'est la plus engageante."""
        return {
            "catalogue": Capacite(
                nom="catalogue", action="read",
                description="La liste des toolboxes Drift (media, timeline, effects...).",
                ecriture=False),
            "boite_a_outils": Capacite(
                nom="boite_a_outils", action="read",
                description="Le schéma JSON réel d'une toolbox Drift, par son nom.",
                ecriture=False),
            "etat_projet": Capacite(
                nom="etat_projet", action="read",
                description="L'état complet du projet ouvert dans Drift (clips, effets, jobs).",
                ecriture=False),
            "capture": Capacite(
                nom="capture", action="read",
                description="Une image fixe (JPEG) de la composition actuelle.",
                ecriture=False),
            "appliquer": Capacite(
                nom="appliquer", action="apply",
                description="Applique une liste d'opérations validées sur le projet Drift ouvert.",
                ecriture=True),
        }

    def sonder(self) -> Sante:
        """Demande la liste des outils. Un port ouvert ne prouve rien."""
        from core.connectors.base import _maintenant

        client = self._client()
        if client is None:
            manque = "DRIFT_MCP_URL absent." if not _base_url() else "DRIFT_MCP_TOKEN absent."
            return Sante(
                etat=EtatSante.NON_CONFIGURE, message=manque,
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())

        reponse = client.outils()
        if not reponse.ok:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"Drift ne répond pas sur {client.url} ({reponse.raison}).",
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())

        noms = {str((outil or {}).get("name") or "")
                for outil in (reponse.resultat.get("tools") or [])}
        if OUTIL_APPLIQUER not in noms:
            return Sante(
                etat=EtatSante.EN_PANNE,
                message=(f"Drift répond mais n'annonce pas {OUTIL_APPLIQUER} "
                         f"({len(noms)} outil(s) vus)."),
                mesure_le=_maintenant())
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message=f"Drift répond : {len(noms)} outil(s), édition disponible.",
            mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : le jeton voyage dans l'en-tête de chaque appel MCP, il n'y
        a pas de poignée de main d'authentification séparée à réussir ici."""
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        client = self._client()
        if client is None:
            return non_configure(action=capacite.nom, cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE)

        outil, acceptes = ROUTES[capacite.nom]
        arguments = {cle: valeur for cle, valeur in parametres.items()
                     if cle in acceptes and valeur is not None}

        if capacite.nom == "boite_a_outils" and not arguments.get("name"):
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun nom de toolbox : rien à décrire.")
        if capacite.nom == "appliquer":
            ops = arguments.get("ops")
            if not isinstance(ops, list) or not ops:
                return echec(action=capacite.nom, cible=self.nom,
                             message="Aucune opération à appliquer.")

        reponse = client.appeler(outil, arguments)
        if not reponse.ok:
            if "Connect" in reponse.raison or "HTTP 4" in reponse.raison:
                return non_configure(action=capacite.nom, cible=self.nom,
                                     ce_qui_manque=CE_QUI_MANQUE, detail_erreur=reponse.raison)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Drift a refusé l'appel : {reponse.raison}.", outil=outil)

        erreur = reponse.erreur_applicative
        if erreur is not None:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Drift a refusé : {erreur}", outil=outil)

        donnees = reponse.donnees()
        return succes(
            action=capacite.nom, cible=self.nom,
            message=self._resume(capacite.nom, arguments, donnees),
            preuve=self._preuve(capacite.nom, arguments, donnees),
            donnees=donnees,
            outil=outil,
        )

    @staticmethod
    def _preuve(nom: str, arguments: Dict[str, Any], donnees: Any) -> str:
        """Une preuve textuelle réelle — jamais « Drift a répondu » seul,
        toujours ce qui a concrètement été demandé ou reçu."""
        if nom == "appliquer":
            ops = arguments.get("ops") or []
            return f"apply : {len(ops)} opération(s) appliquée(s)"
        if nom == "boite_a_outils":
            return f"toolbox : {arguments.get('name')}"
        if isinstance(donnees, dict) and donnees:
            return f"{nom} : {len(donnees)} clé(s) rendue(s)"
        return f"{nom} a répondu"

    @staticmethod
    def _resume(nom: str, arguments: Dict[str, Any], donnees: Any) -> str:
        if nom == "appliquer":
            ops = arguments.get("ops") or []
            return f"{len(ops)} opération(s) appliquée(s) sur le projet Drift ouvert."
        return f"Drift a répondu pour {nom}."
