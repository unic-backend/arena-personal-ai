"""Adaptateur ARENA vers le moteur MIT @pilio/gemini-watermark-remover.

Le moteur reste un composant externe versionne. ARENA ne recopie pas son
algorithme : il l'invoque par son CLI, borne son temps d'execution et valide
l'artefact produit avec son propre contrat image.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.production.artefact_image import valider_image

GWR_BINAIRE = "gwr"
TIMEOUT_SECONDES = 120


@dataclass(frozen=True)
class ResultatNettoyage:
    ok: bool
    sortie: Path | None = None
    erreur: str = ""
    details: dict | None = None


def retirer_filigrane_gemini(entree: Path, sortie: Path) -> ResultatNettoyage:
    entree = entree.resolve()
    sortie = sortie.resolve()
    if not entree.is_file():
        return ResultatNettoyage(False, erreur=f"Fichier source introuvable : {entree}")

    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.unlink(missing_ok=True)
    commande = [GWR_BINAIRE, "remove", str(entree), "--output", str(sortie), "--overwrite", "--json"]
    try:
        proc = subprocess.run(
            commande, capture_output=True, text=True, timeout=TIMEOUT_SECONDES, check=False
        )
    except FileNotFoundError:
        return ResultatNettoyage(False, erreur="Moteur Gemini watermark non installe.")
    except subprocess.TimeoutExpired:
        sortie.unlink(missing_ok=True)
        return ResultatNettoyage(False, erreur="Nettoyage Gemini expire (timeout).")

    if proc.returncode != 0:
        sortie.unlink(missing_ok=True)
        message = (proc.stderr or proc.stdout or "Erreur inconnue du moteur.").strip()
        return ResultatNettoyage(False, erreur=message[-1000:])

    validation = valider_image(sortie)
    if not validation.valide:
        sortie.unlink(missing_ok=True)
        return ResultatNettoyage(False, erreur=f"Sortie image invalide : {validation.raison}")

    details = None
    texte = proc.stdout.strip()
    if texte:
        try:
            details = json.loads(texte)
        except json.JSONDecodeError:
            details = {"sortie_moteur": texte[-1000:]}

    return ResultatNettoyage(True, sortie=sortie, details=details)
