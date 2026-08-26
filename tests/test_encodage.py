"""Encodage des fichiers du dépôt.

Un BOM UTF-8 en tête de fichier est invisible à la lecture et casse des outils
qui lisent la première ligne : un `grep '^import'` ne voyait pas le premier
import de dix modules, ce qui a failli faire oublier `httpx` et `PyYAML` dans
`requirements.txt`.
"""
from pathlib import Path

BOM = b"\xef\xbb\xbf"
RACINE = Path(__file__).resolve().parent.parent
DOSSIERS_IGNORES = {".git", ".venv", "venv", "node_modules", "__pycache__", "data", "media"}


def fichiers_du_depot():
    for chemin in RACINE.rglob("*"):
        if not chemin.is_file():
            continue
        if DOSSIERS_IGNORES & set(chemin.relative_to(RACINE).parts):
            continue
        yield chemin


def test_aucun_fichier_ne_commence_par_un_bom():
    coupables = [
        str(f.relative_to(RACINE))
        for f in fichiers_du_depot()
        if f.read_bytes().startswith(BOM)
    ]

    assert coupables == [], f"BOM UTF-8 en tête de : {coupables}"


def test_le_premier_import_de_chaque_module_est_lisible_ligne_a_ligne():
    """Le symptôme concret du BOM : la première ligne devient illisible telle quelle."""
    illisibles = []
    for f in fichiers_du_depot():
        if f.suffix != ".py":
            continue
        with f.open(encoding="utf-8") as fichier:
            premiere = fichier.readline()
        if premiere.startswith("﻿"):
            illisibles.append(str(f.relative_to(RACINE)))

    assert illisibles == []
