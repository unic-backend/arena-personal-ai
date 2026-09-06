"""Connecteur de génération IFC — un croquis de cloison DÉJÀ CALCULÉ, écrit
sur disque. Voir `core/production/ifc_generation.py` pour le pourquoi (pas
de second moteur BIM, l'API d'IfcOpenShell suffit).

Même logique que le devis (DEC-0041) et `ui_generate` (DEC-0050) : le
fichier reste local, dans `media/rendered/`, relu avant d'être partagé —
`ALLOWED` sous `WRITE_FILES`, pas de confirmation préalable.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.production.ifc_generation import EPAISSEUR_DEFAUT_M, generer_croquis_cloison

logger = logging.getLogger("usman.connecteurs.ifc_generation")

#: Bornes de sécurité — jamais une cote absurde ecrite dans un fichier envoye
#: sans relecture (meme discipline que les autres validations du depot).
LONGUEUR_MAX_M = 100.0
HAUTEUR_MAX_M = 10.0
EPAISSEUR_MAX_M = 1.0


def _slug(titre: str) -> str:
    normalise = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode("ascii")
    normalise = re.sub(r"[^a-zA-Z0-9]+", "-", normalise).strip("-").lower()
    return normalise[:60] or "cloison"


class ConnecteurIfcGeneration(Connecteur):
    """Écrit un croquis IFC minimal (une cloison) à partir de dimensions déjà données."""

    service = "ifc_generation"
    nom = "ifc_generation"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else RENDERED_DIR

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "generer": Capacite(
                nom="generer", action="document",
                description="Écrit un croquis IFC minimal d'une cloison (longueur x hauteur).",
                ecriture=True),
        }

    def authentifier(self) -> bool:
        return True

    def sonder(self) -> Sante:
        try:
            import ifcopenshell  # noqa: F401
        except ImportError:
            return Sante(
                etat=EtatSante.NON_CONFIGURE, message="IfcOpenShell n'est pas installé.",
                ce_qui_manque="pip install ifcopenshell (déjà utilisé en lecture, DEC-0053).",
                mesure_le=_maintenant())
        return Sante(etat=EtatSante.OPERATIONNEL, message="IfcOpenShell est installé.",
                     mesure_le=_maintenant())

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        try:
            longueur_m = float(parametres.get("longueur_m"))
            hauteur_m = float(parametres.get("hauteur_m"))
        except (TypeError, ValueError):
            return echec(action=capacite.nom, cible=self.nom,
                         message="`longueur_m` et `hauteur_m` doivent être des nombres.")

        epaisseur_brut = parametres.get("epaisseur_m")
        try:
            epaisseur_m = float(epaisseur_brut) if epaisseur_brut is not None else EPAISSEUR_DEFAUT_M
        except (TypeError, ValueError):
            return echec(action=capacite.nom, cible=self.nom,
                         message="`epaisseur_m` doit être un nombre.")

        nom = str(parametres.get("nom") or "Cloison proposée").strip() or "Cloison proposée"

        if not 0 < longueur_m <= LONGUEUR_MAX_M:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"`longueur_m` doit rester entre 0 et {LONGUEUR_MAX_M:g}.")
        if not 0 < hauteur_m <= HAUTEUR_MAX_M:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"`hauteur_m` doit rester entre 0 et {HAUTEUR_MAX_M:g}.")
        if not 0 < epaisseur_m <= EPAISSEUR_MAX_M:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"`epaisseur_m` doit rester entre 0 et {EPAISSEUR_MAX_M:g}.")

        try:
            fichier = generer_croquis_cloison(longueur_m, hauteur_m, epaisseur_m, nom)
        except ImportError:
            return non_configure(
                action=capacite.nom, cible=self.nom,
                ce_qui_manque="pip install ifcopenshell (déjà utilisé en lecture, DEC-0053).")
        except Exception as erreur:  # noqa: BLE001 — une generation ratee est un echec, jamais un crash
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Génération impossible : {erreur}")

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / f"croquis-{_slug(nom)}-{int(time.time())}.ifc"
        try:
            fichier.write(str(sortie))
        except OSError as erreur:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le fichier n'a pas pu être écrit : {erreur}")

        if not sortie.is_file() or sortie.stat().st_size == 0:
            return echec(action=capacite.nom, cible=self.nom,
                         message="L'écriture s'est terminée sans laisser de fichier réel.")

        url = f"/media/rendered/{sortie.name}" if self.dossier == RENDERED_DIR else None
        detail: Dict[str, Any] = {
            "longueur_m": longueur_m, "hauteur_m": hauteur_m, "epaisseur_m": epaisseur_m,
            "surface_m2": round(longueur_m * hauteur_m, 4),
        }
        if url:
            detail["url"] = url

        return succes(
            action=capacite.nom, cible=self.nom,
            message=(f"Croquis IFC de « {nom} » écrit ({longueur_m:g} m x {hauteur_m:g} m, "
                     f"{sortie.stat().st_size} octets)."),
            preuve=str(sortie), **detail)
