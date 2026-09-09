"""Un PDF écrit n'est valide que rouvert et compté — jamais parce
qu'`écrire()` n'a pas levé. Même discipline que `core/production/
conversion/validation.py` (DEC-0074) : un moteur qui rend sans lever n'a
encore rien prouvé.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def verifier(chemin: Path, pages_attendues: Optional[int] = None) -> Optional[str]:
    """`None` si `chemin` est un PDF réel, réouvrable, avec le nombre de
    pages attendu quand il est connu. Sinon la raison du refus."""
    if not chemin.is_file():
        return "aucun fichier écrit"
    if chemin.stat().st_size == 0:
        return "fichier écrit mais vide"

    try:
        from pypdf import PdfReader
        lecteur = PdfReader(str(chemin))
        n = len(lecteur.pages)
    except Exception as erreur:  # noqa: BLE001 — le PDF ecrit est illisible, c'est l'echec a rapporter
        return f"PDF écrit mais illisible : {type(erreur).__name__}: {erreur}"

    if n == 0:
        return "PDF écrit sans aucune page"
    if pages_attendues is not None and n != pages_attendues:
        return f"PDF écrit avec {n} page(s), {pages_attendues} attendue(s)"
    return None
