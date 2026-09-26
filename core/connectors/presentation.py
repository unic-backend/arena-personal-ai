"""Connecteur de présentations éditables, natif Arena."""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.production.presentations import PresentationInvalide, generer_pptx


def _slug(value: str) -> str:
    normalise = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", normalise).strip("-").lower()[:60] or "presentation"


class ConnecteurPresentation(Connecteur):
    service = "presentation"
    nom = "presentation"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else RENDERED_DIR / "presentations"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "generer": Capacite(
                nom="generer", action="document",
                description="Génère un PPTX éditable depuis un plan structuré de slides.",
                ecriture=True,
            )
        }

    def authentifier(self) -> bool:
        return True

    def sonder(self) -> Sante:
        try:
            import pptx  # noqa: F401
        except ImportError:
            return Sante(etat=EtatSante.NON_CONFIGURE, message="python-pptx absent.",
                         ce_qui_manque="pip install python-pptx", mesure_le=_maintenant())
        return Sante(etat=EtatSante.OPERATIONNEL, message="python-pptx disponible.",
                     mesure_le=_maintenant())

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        plan = parametres.get("plan")
        if isinstance(plan, str):
            try:
                plan = json.loads(plan)
            except json.JSONDecodeError as erreur:
                return echec(capacite.nom, self.nom, f"Plan JSON invalide : {erreur.msg}.")
        if not isinstance(plan, dict):
            return echec(capacite.nom, self.nom, "plan doit être un objet JSON.")
        titre = str(plan.get("titre") or "presentation")
        sortie = self.dossier / f"{_slug(titre)}-{int(time.time())}.pptx"
        try:
            detail = generer_pptx(plan, sortie)
        except ImportError:
            return non_configure(capacite.nom, self.nom, "pip install python-pptx")
        except (PresentationInvalide, OSError, ValueError) as erreur:
            sortie.unlink(missing_ok=True)
            return echec(capacite.nom, self.nom, f"Génération PPTX impossible : {erreur}")
        if not sortie.is_file() or sortie.stat().st_size == 0:
            return echec(capacite.nom, self.nom, "Aucun fichier PPTX réel n'a été produit.")
        url = (f"/media/rendered/presentations/{sortie.name}"
               if self.dossier == RENDERED_DIR / "presentations" else None)
        if url:
            detail["url"] = url
        detail["taille_octets"] = sortie.stat().st_size
        return succes(capacite.nom, self.nom,
                      f"Présentation « {detail['titre']} » générée ({detail['slides']} slides).",
                      preuve=str(sortie), **detail)
