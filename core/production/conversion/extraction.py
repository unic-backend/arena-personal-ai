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


def pdf_vers_docx(entree: Path, sortie: Path) -> None:
    """PDF -> Word sans LibreOffice : le texte du PDF, dans un Word modifiable
    (DEC-0172).

    `pdf -> docx` n'avait qu'un moteur, LibreOffice. Sur une machine qui ne
    l'a pas — un PC Windows ordinaire — « convertis ce PDF en Word »
    echouait. Ce moteur passe APRES LibreOffice, qui garde la mise en page
    quand il est la.

    Ce qu'il fait, sans pretendre plus : le texte que le lecteur a lu, une
    ligne du PDF par paragraphe (recoller les lignes en phrases casserait
    listes et tableaux sans le dire), un saut de page entre deux pages, et
    une note en tete de toute page lue par OCR.
    """
    from docx import Document
    from docx.enum.text import WD_BREAK

    lu = lire_document(entree)
    if not lu.lu:
        raise MoteurEchec(f"document non lu ({lu.statut}) : {lu.raison}")
    document = Document()
    for numero, passage in enumerate(lu.passages):
        if numero:
            document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        if passage.via_ocr:
            note = document.add_paragraph().add_run(
                f"Page {passage.page} lue par reconnaissance de caracteres (OCR) : a relire.")
            note.italic = True
        for ligne in passage.texte.splitlines():
            if ligne.strip():
                document.add_paragraph(ligne.strip())
    document.save(str(sortie))
