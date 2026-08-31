"""Connecteur OpenTakeoff — le metre d'un plan PDF, mesure par le vrai moteur.

OpenTakeoff (Kentucky-ai, Apache-2.0) est un moteur de metre de plans de
construction. Comme WanGP et MoneyPrinterTurbo (DEC-0008) : **un service
separe**, installe a cote — jamais dans ce depot — que le proprietaire construit
une fois sur sa machine. La difference avec les deux autres : il ne parle pas
HTTP. Son serveur MCP (`mcp/server.ts`, lu dans son propre depot) n'expose que
`StdioServerTransport` — le protocole vit sur l'entree/sortie standard d'un
processus Node, pas sur un port. `core/mcp/stdio_transport.py` porte ce
transport ; ce module l'utilise sans en reimplementer une ligne.

**Ce qui est mesure ici, et pourquoi c'est un sous-ensemble des quarante
outils du serveur** : le moteur sait aussi faire cliquer une piece a la main,
marquer un rectangle autour d'un symbole repete, comparer des revisions —
tout ce qui suppose de DESIGNER un point ou un rectangle sur l'image du plan.
Un modele de texte ne voit pas le plan ; lui faire deviner des coordonnees
produirait un metre faux avec l'air d'un metre juste. Ce qui est branche ici
se fait sans deviner une coordonnee : `detect_rooms` lit les numeros de piece
deja ecrits sur le plan et flotte chaque piece lui-meme (le meme moteur que
le clic humain), `derive_base` en tire le perimetre, et `count_marks`
(`compter_marques`, DEC-0022) recense les marques annotees deja ecrites sur
le plan (un tag de menuiserie au-dessus d'une valeur) — texte, pas image,
donc sans deviner de coordonnee non plus.

Compter un symbole repete par une marquee (`symbol_sweep`) ou deduire une
ouverture precise (`cut_out`) restent hors de portee **tant que rien n'a
mesure si un modele de vision peut vraiment designer un rectangle sur
l'image avec une precision suffisante** — `SUGGESTION — NON IMPLEMENTEE`,
pas simulees. Qwen3-VL (DEC-0019) existe, mais personne n'a jamais mesure
sa capacite a pointer un symbole en pixels sur cette machine (pas de GPU).

**Quatre regles :**

1. **Sans echelle mesuree sur une feuille, cette feuille n'est pas comptee.**
   `set_scale(use_detected=True)` echoue sur une feuille sans cartouche lisible
   ; cette feuille est rapportee a part (`echelle_manquante`), jamais avec des
   quantites en pixels deguisees en metres.

2. **Le moteur choisit ce qu'il flotte, jamais un chiffre suppose.** Une
   piece que `detect_rooms` retient (`withheld`) n'entre dans aucun total —
   elle est comptee, nommee, et rendue telle quelle.

3. **Mesurer n'ecrit rien ; exporter est une confirmation.** `mesurer`
   n'ouvre le plan qu'en memoire du processus MCP, jamais sur disque hors
   ce que le moteur y lit deja. `exporter` produit deux fichiers reels — le
   rapport et le jeu de plans marque — et passe donc par la meme porte que le
   devis PDF : confirmation, `WRITE_FILES`.

4. **Le processus ne survit jamais a l'appel.** `ClientMcpStdio` est ouvert
   et ferme dans le meme `_executer` — jamais de processus Node qui traine
   entre deux demandes.
"""
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.mcp.stdio_transport import ClientMcpStdio, Reponse

logger = logging.getLogger("usman.connecteurs.opentakeoff")

#: Le dossier `mcp/` d'un clone construit d'OpenTakeoff (jamais dans ce depot).
DOSSIER_MCP = os.getenv("OPENTAKEOFF_MCP_DIR", "").strip()

#: Le binaire Node a lancer. Reglable : sa machine peut en avoir plusieurs.
NODE_BIN = os.getenv("OPENTAKEOFF_NODE_BIN", "node").strip() or "node"

CE_QUI_MANQUE = (
    "OpenTakeoff construit a cote (jamais dans ce depot, DEC-0008) : "
    "scripts/installer_opentakeoff.ps1, ou a la main — cloner "
    "https://github.com/Kentucky-ai/opentakeoff, puis dans le clone "
    "`cd web && npm install` et `cd ../mcp && npm install && npm run build`. "
    "OPENTAKEOFF_MCP_DIR doit ensuite pointer vers son dossier mcp/."
)

DUREE_SONDE_SECONDES = 60.0

#: Etiquette interne sous laquelle les pieces detectees se rangent. Jamais
#: montree telle quelle : `metre_plan.py` la traduit en francais.
CONDITION_SURFACE = "ARENA-SURFACE-1"
CONDITION_PERIMETRE = "ARENA-PERIMETRE-1"


def _commande() -> Optional[List[str]]:
    """La commande a lancer, ou None si rien n'est configure ou construit."""
    if not DOSSIER_MCP:
        return None
    if not (Path(DOSSIER_MCP) / "dist" / "server.js").is_file():
        return None
    return [NODE_BIN, "dist/server.js"]


def _erreur_outil(reponse: Reponse) -> Optional[str]:
    """Le message d'une erreur APPLICATIVE (`isError`), distincte d'une panne
    de transport. Une reponse `ok=True` peut porter un echec de l'outil :
    mesure sur le serveur reel — un outil inconnu et une feuille non chargee
    rendent tous deux `ok=True, isError=True`."""
    if not isinstance(reponse.resultat, dict) or not reponse.resultat.get("isError"):
        return None
    return reponse.contenu_texte or "erreur non precisee"


class ConnecteurOpenTakeoff(Connecteur):
    """Metre un plan PDF avec le moteur OpenTakeoff, en session courte."""

    service = "takeoff"
    nom = "opentakeoff"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0
        self._derniere_erreur: str = ""

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "mesurer": Capacite(
                nom="mesurer", action="read",
                description="Mesure les surfaces et longueurs d'un plan PDF, sans rien ecrire.",
                ecriture=False),
            "exporter": Capacite(
                nom="exporter", action="export",
                description="Ecrit le rapport de metre et le plan marque, a cote du plan source.",
                ecriture=True),
            "compter_marques": Capacite(
                nom="compter_marques", action="read",
                description=(
                    "Recense les marques annotees (ex. un tableau de menuiseries "
                    "D1/W1) deja ecrites sur le plan, sans rien ecrire."),
                ecriture=False),
        }

    def authentifier(self) -> bool:
        """Vrai : un processus local, sans identifiant a presenter."""
        return True

    # --- Sante ------------------------------------------------------------------

    def sonder(self) -> Sante:
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        commande = _commande()
        if commande is None:
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="OpenTakeoff non construit : OPENTAKEOFF_MCP_DIR absent ou dist/server.js introuvable.",
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            with ClientMcpStdio(commande, dossier=DOSSIER_MCP) as client:
                reponse = client.outils()
            if reponse.ok:
                nombre = len(reponse.resultat.get("tools", []))
                sante = Sante(etat=EtatSante.OPERATIONNEL,
                              message=f"OpenTakeoff repond : {nombre} outil(s) annonce(s).",
                              mesure_le=_maintenant())
            else:
                sante = Sante(
                    etat=EtatSante.EN_PANNE,
                    message=f"OpenTakeoff construit mais ne repond pas : {reponse.raison}",
                    mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution ----------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        chemin = str(parametres.get("chemin") or "").strip()
        if not chemin:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun chemin de plan fourni : rien a mesurer.")
        if not Path(chemin).is_file():
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Aucun fichier a ce chemin : {chemin}")

        commande = _commande()
        if commande is None:
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)

        with ClientMcpStdio(commande, dossier=DOSSIER_MCP) as client:
            if capacite.nom == "compter_marques":
                return self._compter_marques(client, chemin, parametres.get("marques"))

            mesure = self._mesurer_session(client, chemin)
            if mesure is None:
                return echec(action=capacite.nom, cible=self.nom,
                             message=self._derniere_erreur)

            if capacite.nom == "mesurer":
                return succes(
                    action=capacite.nom, cible=self.nom,
                    message=(f"{mesure['pieces_totales']} piece(s) mesuree(s) sur "
                             f"{mesure['feuilles_totales']} feuille(s)."),
                    preuve=chemin, **mesure)

            # "exporter" : le meme metre, puis les deux fichiers reels.
            defaut = Path(chemin).with_suffix("")
            chemin_rapport = str(parametres.get("chemin_rapport") or f"{defaut} - rapport.json")
            reponse_rapport = client.appeler("export_report", {
                "path": chemin_rapport,
                "project_name": str(parametres.get("projet") or Path(chemin).stem),
                "overwrite": True,
            })
            erreur_rapport = _erreur_outil(reponse_rapport)
            if not reponse_rapport.ok or erreur_rapport:
                return echec(action=capacite.nom, cible=self.nom,
                             message=f"Rapport non ecrit : {erreur_rapport or reponse_rapport.raison}")

            arguments_marque: Dict[str, Any] = {"overwrite": True}
            if parametres.get("chemin_marque"):
                arguments_marque["path"] = str(parametres["chemin_marque"])
            reponse_marque = client.appeler("export_marked_pdf", arguments_marque)
            erreur_marque = _erreur_outil(reponse_marque)
            if not reponse_marque.ok or erreur_marque:
                return echec(action=capacite.nom, cible=self.nom,
                             message=f"Plan marque non ecrit : {erreur_marque or reponse_marque.raison}")

            donnees_marque = reponse_marque.donnees() or {}
            return succes(
                action=capacite.nom, cible=self.nom,
                message=f"Rapport et plan marque ecrits pour {Path(chemin).name}.",
                preuve=donnees_marque.get("path") or chemin_rapport,
                chemin_rapport=chemin_rapport,
                chemin_marque=donnees_marque.get("path"),
                **mesure)

    # --- Le decompte de marques, sans image ni coordonnee ---------------------------

    def _compter_marques(self, client: ClientMcpStdio, chemin: str,
                         marques: Optional[List[str]]) -> ResultatAction:
        """Recense les marques annotees deja ecrites sur le plan (`count_marks`).

        Aucune echelle requise (le decompte est en unites, EA — jamais une
        longueur ni une surface), et aucune coordonnee n'est designee : l'outil
        lit le texte deja present sur le plan (un tag de menuiserie au-dessus
        d'une valeur, comme un tableau de portes/fenetres), jamais une image.
        C'est le seul des trois outils "symboles" du serveur qui ne suppose pas
        qu'un modele regarde l'image — voir la docstring du module.
        """
        reponse_ouverture = client.appeler("load_plan", {"path": chemin})
        erreur_ouverture = _erreur_outil(reponse_ouverture)
        if not reponse_ouverture.ok or erreur_ouverture:
            return echec(action="compter_marques", cible=self.nom,
                         message=f"Plan illisible : {erreur_ouverture or reponse_ouverture.raison}")

        arguments: Dict[str, Any] = {"commit": False}
        if marques:
            arguments["marks"] = list(marques)
        reponse = client.appeler("count_marks", arguments)
        erreur = _erreur_outil(reponse)
        if not reponse.ok or erreur:
            return echec(action="compter_marques", cible=self.nom,
                         message=f"Decompte impossible : {erreur or reponse.raison}")

        donnees = reponse.donnees() or {}
        return succes(
            action="compter_marques", cible=self.nom,
            message=f"{donnees.get('total', 0)} marque(s) recensee(s).",
            preuve=chemin,
            marques=donnees.get("marks", []),
            total=donnees.get("total", 0),
            complet=donnees.get("complete", True),
            feuilles_ignorees=donnees.get("skipped", []),
        )

    # --- Le metre lui-meme, partage entre les deux capacites -----------------------

    def _mesurer_session(self, client: ClientMcpStdio, chemin: str) -> Optional[Dict[str, Any]]:
        """Ouvre le plan, mesure chaque feuille exploitable, rend le total.

        Rend `None` sur un echec qui empeche toute mesure (le detail est dans
        `self._derniere_erreur`). Une feuille sans echelle detectee n'arrete
        pas les autres : elle est nommee dans `feuilles_sans_echelle`.
        """
        self._derniere_erreur = ""
        reponse = client.appeler("load_plan", {"path": chemin})
        erreur = _erreur_outil(reponse)
        if not reponse.ok or erreur:
            self._derniere_erreur = f"Plan illisible : {erreur or reponse.raison}"
            return None

        feuilles = (reponse.donnees() or {}).get("sheets", [])
        if not feuilles:
            self._derniere_erreur = "Le plan ne contient aucune feuille exploitable."
            return None

        pieces: List[Dict[str, Any]] = []
        feuilles_sans_echelle: List[str] = []
        feuilles_mesurees: List[str] = []

        for feuille in feuilles:
            cle = feuille.get("sheet")
            reponse_echelle = client.appeler("set_scale", {"sheet": cle, "use_detected": True})
            if not reponse_echelle.ok or _erreur_outil(reponse_echelle):
                feuilles_sans_echelle.append(cle)
                continue

            reponse_pieces = client.appeler("detect_rooms", {
                "sheet": cle, "condition": CONDITION_SURFACE,
            })
            if not reponse_pieces.ok or _erreur_outil(reponse_pieces):
                feuilles_sans_echelle.append(cle)
                continue

            feuilles_mesurees.append(cle)
            donnees = reponse_pieces.donnees() or {}
            for piece in donnees.get("rooms", []):
                pieces.append({
                    "feuille": cle,
                    "numero": piece.get("label"),
                    "surface_pi2": piece.get("area_sf"),
                    "perimetre_pi": piece.get("perimeter_lf"),
                    "confiance": piece.get("confidence"),
                })

        if not feuilles_mesurees:
            self._derniere_erreur = (
                "Aucune feuille n'a d'echelle exploitable : "
                f"{', '.join(feuilles_sans_echelle) or 'aucune feuille'}. "
                "Indique l'echelle a la main (ex. 1/4\" = 1'-0\") sur le plan avant de le redeposer.")
            return None

        reponse_base = client.appeler("derive_base", {
            "source_condition": CONDITION_SURFACE, "condition": CONDITION_PERIMETRE,
        })
        base_indisponible = not reponse_base.ok or bool(_erreur_outil(reponse_base))

        reponse_resume = client.appeler("takeoff_summary")
        resume = reponse_resume.donnees() if reponse_resume.ok and not _erreur_outil(reponse_resume) else {}

        return {
            "pieces": pieces,
            "pieces_totales": len(pieces),
            "feuilles_totales": len(feuilles),
            "feuilles_mesurees": feuilles_mesurees,
            "feuilles_sans_echelle": feuilles_sans_echelle,
            "perimetre_disponible": not base_indisponible,
            "resume": resume,
        }
