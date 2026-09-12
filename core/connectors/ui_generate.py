"""Connecteur de generation d'interface : recoit du code DEJA GENERE, le
valide, l'ecrit en artefact.

Suite de `core/production/ui_generation.py` — lire son en-tete d'abord : ce
qui a motive ce module (integrer OpenUI), et pourquoi c'est la TECHNIQUE de
prompt qui est reprise, jamais le serveur FastAPI d'OpenUI (qui exige une
connexion GitHub et tire weave/boto3/peewee/fastapi-sso pour un usage
hebergement qu'ARENA n'a pas).

Ce connecteur ne genere jamais de code lui-meme : c'est `agents/ui/
ui_agent.py` qui appelle le modele (ARENA local d'abord, DEC-0002) et lui
transmet le resultat. Meme separation que Xaar Kaname/KrillinAI : l'agent
compose, le connecteur execute et fait respecter les permissions — un code
genere hors des permissions serait un code genere hors de tout controle.

**Deux regles :**

1. **Aucun script externe hors d'une liste fermee.** Un `<script src="...">`
   vers un domaine non reconnu (`core/production/ui_generation.py::
   DOMAINES_SCRIPT_AUTORISES`) fait REFUSER l'ecriture entierement — pas un
   avertissement glisse a cote d'un fichier quand meme ecrit. Le mandat de
   la mission (« controle des URLs externes ») est une porte, pas une note.
2. **Ecrit dans `media/rendered/`, comme le devis.** Meme dossier, meme
   route deja servie (`GET /media/rendered/{nom:path}`) : une interface generee
   est ouvrable depuis le telephone sans route nouvelle.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.production.ui_generation import FRAMEWORKS, valider_scripts_externes

logger = logging.getLogger("usman.connecteurs.ui_generate")

EXTENSIONS = {"html": ".html", "react": ".jsx", "svelte": ".svelte", "web-component": ".js"}

#: Une generation raisonnable a une taille — un modele qui boucle ou qui
#: rend un flux mal coupe ne doit pas produire un fichier de plusieurs
#: dizaines de Mo sans que rien ne le remarque.
TAILLE_MAX_OCTETS = 2_000_000


def _slug(titre: str) -> str:
    normalise = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode("ascii")
    normalise = re.sub(r"[^a-zA-Z0-9]+", "-", normalise).strip("-").lower()
    return normalise[:60] or "interface"


class ConnecteurUiGenerate(Connecteur):
    """Un code d'interface DEJA GENERE, valide puis ecrit — jamais genere ici."""

    service = "ui_generate"
    nom = "ui_generate"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else RENDERED_DIR

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "generer": Capacite(
                nom="generer", action="document",
                description="Valide et ecrit un code d'interface deja genere par un modele.",
                ecriture=True),
        }

    def sonder(self) -> Sante:
        """Toujours OPERATIONNEL : ce module ne depend d'aucun moteur
        externe — Python pur, comme le garde de chemin de GitIngest."""
        return Sante(etat=EtatSante.OPERATIONNEL,
                     message="Validation et ecriture locales, aucun moteur externe.",
                     mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : aucun identifiant, aucun service exterieur."""
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        code = str(parametres.get("code") or "")
        framework = str(parametres.get("framework") or "html").strip().lower()
        titre = str(parametres.get("titre") or "interface").strip()

        if not code.strip():
            return echec(action=capacite.nom, cible=self.nom, message="Aucun code fourni.")
        if framework not in FRAMEWORKS:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Framework « {framework} » inconnu. "
                                 f"Valides : {', '.join(sorted(FRAMEWORKS))}.")
        if len(code.encode("utf-8")) > TAILLE_MAX_OCTETS:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Code genere trop volumineux (> {TAILLE_MAX_OCTETS} octets).")

        problemes = valider_scripts_externes(code)
        if problemes:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Ecriture refusee : " + "; ".join(problemes),
                         problemes=problemes)

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / f"ui-{_slug(titre)}-{int(time.time())}{EXTENSIONS[framework]}"
        try:
            sortie.write_text(code, encoding="utf-8")
        except OSError as erreur:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le fichier n'a pas pu etre ecrit : {erreur}")

        if not sortie.is_file() or sortie.stat().st_size == 0:
            return echec(action=capacite.nom, cible=self.nom,
                         message="L'ecriture s'est terminee sans laisser de fichier reel.")

        url = f"/media/rendered/{sortie.name}" if self.dossier == RENDERED_DIR else None
        detail: Dict[str, Any] = {"framework": framework, "octets": sortie.stat().st_size}
        if url:
            detail["url"] = url

        return succes(action=capacite.nom, cible=self.nom,
                     message=f"Interface « {titre} » ecrite ({framework}, {sortie.stat().st_size} octets).",
                     preuve=str(sortie), **detail)
