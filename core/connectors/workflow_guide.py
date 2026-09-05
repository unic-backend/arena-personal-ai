"""Connecteur du guide de procedure : un workflow deja decrit, ecrit en document.

Suite de `core/production/workflow_guide.py` — lire son en-tete d'abord : ce
qui a motive ce module, et ce qui a ete explicitement refuse (la capture en
direct d'une session navigateur, faute de besoin reel et parce que c'est une
surface de captation). Ce connecteur n'observe jamais rien : il recoit un
workflow deja ecrit (titre, etapes, captures d'ecran deja existantes) et
produit un fichier — PDF, DOCX, HTML ou Markdown.

**Deux regles, en plus de celles du module qu'il enveloppe :**

1. **Ecrit dans `media/rendered/`, comme le devis.** Meme dossier, meme route
   deja servie (`GET /media/rendered/{nom}`, `apps/backend/main.py`) : un
   guide produit est atteignable depuis le telephone sans qu'une seule ligne
   de route n'ait a etre ajoutee.
2. **`ecriture=True`, sous `WRITE_FILES`** — la meme protection que le devis
   (DEC-0041) et Graphify. Une lecture (« quelles etapes ce guide
   contient-il ? ») n'existe pas ici : produire EST l'action.
"""
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.production.workflow_guide import (
    Etape,
    Workflow,
    valider_captures,
    vers_docx,
    vers_html,
    vers_markdown,
    vers_pdf,
)

logger = logging.getLogger("usman.connecteurs.workflow_guide")

FORMATS_VALIDES = frozenset({"pdf", "docx", "html", "markdown"})
EXTENSIONS = {"pdf": ".pdf", "docx": ".docx", "html": ".html", "markdown": ".md"}


def _slug(titre: str) -> str:
    """Un nom de fichier sur a partir du titre — jamais le titre brut, qui
    peut porter des accents/espaces/caracteres que tous les systemes de
    fichiers ne rendent pas pareil."""
    normalise = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode("ascii")
    normalise = re.sub(r"[^a-zA-Z0-9]+", "-", normalise).strip("-").lower()
    return normalise[:60] or "guide"


def _workflow_depuis_parametres(**parametres: Any) -> Workflow:
    etapes_brutes = parametres.get("etapes") or []
    etapes = [
        Etape(
            action=str(e.get("action") or "").strip(),
            description=str(e.get("description") or "").strip(),
            contexte=str(e.get("contexte") or "").strip(),
            capture_ecran=(str(e["capture_ecran"]).strip() if e.get("capture_ecran") else None),
            avertissement=str(e.get("avertissement") or "").strip(),
        )
        for e in etapes_brutes if isinstance(e, dict)
    ]
    return Workflow(
        titre=str(parametres.get("titre") or "").strip(),
        introduction=str(parametres.get("introduction") or "").strip(),
        prerequis=[str(p) for p in (parametres.get("prerequis") or [])],
        etapes=etapes,
        conclusion=str(parametres.get("conclusion") or "").strip(),
    )


class ConnecteurWorkflowGuide(Connecteur):
    """Un workflow deja decrit, transforme en document reel — jamais capture."""

    service = "workflow_guide"
    nom = "workflow_guide"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else RENDERED_DIR

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "generer": Capacite(
                nom="generer", action="document",
                description="Transforme un workflow deja decrit (etapes, captures fournies) en PDF/DOCX/HTML/Markdown.",
                ecriture=True),
        }

    def sonder(self) -> Sante:
        try:
            import docx  # noqa: F401
            import reportlab  # noqa: F401
        except ImportError as erreur:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"Dependance manquante : {erreur}.",
                ce_qui_manque="reportlab et python-docx (deja dans requirements.txt)",
                mesure_le=_maintenant())
        return Sante(etat=EtatSante.OPERATIONNEL,
                     message="reportlab et python-docx sont installes.",
                     mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : aucun identifiant, aucun service exterieur."""
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        format_demande = str(parametres.get("format") or "pdf").strip().lower()
        if format_demande not in FORMATS_VALIDES:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Format « {format_demande} » inconnu. "
                                 f"Formats valides : {', '.join(sorted(FORMATS_VALIDES))}.")

        workflow = _workflow_depuis_parametres(**parametres)
        if not workflow.titre:
            return echec(action=capacite.nom, cible=self.nom, message="Aucun titre donne.")
        if not workflow.etapes:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucune etape donnee : rien a documenter.")

        problemes = valider_captures(workflow)

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / f"guide-{_slug(workflow.titre)}-{int(time.time())}{EXTENSIONS[format_demande]}"

        try:
            if format_demande == "pdf":
                vers_pdf(workflow, sortie)
            elif format_demande == "docx":
                vers_docx(workflow, sortie)
            elif format_demande == "html":
                sortie.write_text(vers_html(workflow), encoding="utf-8")
            else:  # markdown
                sortie.write_text(vers_markdown(workflow), encoding="utf-8")
        except Exception as erreur:  # noqa: BLE001 — une capture illisible/corrompue se rapporte
            logger.info("Guide non produit : %s", erreur)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le document n'a pas pu etre ecrit : {type(erreur).__name__}.")

        if not sortie.exists():
            return echec(action=capacite.nom, cible=self.nom,
                         message="Le rendu s'est termine sans laisser de fichier.")

        url = f"/media/rendered/{sortie.name}" if self.dossier == RENDERED_DIR else None
        avertissements = [f"{p.chemin} : {p.raison}" for p in problemes]
        message = f"Guide « {workflow.titre} » ecrit ({format_demande}, {len(workflow.etapes)} etape(s))."
        if avertissements:
            message += f" {len(avertissements)} capture(s) ignoree(s)."

        detail: Dict[str, Any] = {
            "format": format_demande, "etapes": len(workflow.etapes),
            "octets": sortie.stat().st_size, "captures_ignorees": avertissements,
        }
        if url:
            detail["url"] = url

        return succes(action=capacite.nom, cible=self.nom, message=message,
                     preuve=str(sortie), **detail)
