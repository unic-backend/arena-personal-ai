"""PDF / Word / Excel / PowerPoint -> texte : le lecteur de documents, en fichier.

`tools/documents/reader.py` lit deja ces formats pour les pieces jointes et
le RAG — avec la provenance de chaque passage et l'OCR des pages scannees.
Aucune conversion ne menait pourtant a un `.txt` (DEC-0170) : « sors-moi le
texte de ce PDF » n'avait pas de moteur. Ce module ne relit rien lui-meme,
il ecrit ce que le lecteur a lu.

Deux regles du lecteur sont gardees telles quelles :

- **Un document illisible fait echouer**, avec la raison du lecteur (scanne
  sans OCR, format corrompu) — jamais un fichier texte vide livre comme une
  reussite.
- **Chaque passage dit d'ou il vient** (page, feuille, diapositive), et une
  page lue par OCR porte « (OCR) » : un texte devine ne passe pas pour un
  texte encode.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from core.production.conversion.moteurs import MoteurEchec
from tools.documents.reader import lire_document


def disponible() -> Tuple[bool, str]:
    """Le lecteur s'appuie sur pypdf, python-docx, openpyxl et python-pptx —
    toutes des dependances declarees d'ARENA. Une bibliotheque absente fait
    echouer la lecture de SON format, avec son nom, pas les autres."""
    return True, "lecteur de documents ARENA (tools/documents/reader.py)"


def document_vers_texte(entree: Path, sortie: Path) -> None:
    document = lire_document(entree)
    if not document.lu:
        raise MoteurEchec(f"document non lu ({document.statut}) : {document.raison}")
    plusieurs = len(document.passages) > 1
    morceaux = []
    for passage in document.passages:
        if plusieurs or passage.via_ocr:
            morceaux.append(f"--- {passage.source} ---\n{passage.texte}")
        else:
            morceaux.append(passage.texte)
    sortie.write_text("\n\n".join(morceaux) + "\n", encoding="utf-8")
