"""« Convertis ce fichier en Word » : la phrase qui demande de CONVERTIR une
piece jointe, et le format voulu (DEC-0177).

Trois conditions, toutes necessaires :

1. un verbe de conversion (« convertis », « transforme », « mets », « passe »,
   « exporte ») ;
2. un format cible annonce (« en Word », « au format PDF », « vers Excel ») ;
3. **une reference a un fichier fourni** (« ce fichier », « ce PDF », « la
   piece jointe », « ces documents »).

La troisieme separe cette demande de la redaction : « fais-moi un PDF de ca »
ecrit la REPONSE dans un fichier (`format_de_document_demande`, chat.py) ;
« convertis ce PDF en Word » convertit le fichier ENVOYE. Sans elle, les deux
se confondraient.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

VERBES = (
    "convertis", "convertir", "convertit", "converti ", "conversion",
    "transforme", "transformer", "mets ", "mettre ", "passe ", "passer ",
    "exporte", "exporter", "enregistre", "enregistrer",
)

REFERENCES_A_UN_FICHIER = (
    "ce fichier", "ces fichiers", "ce document", "ces documents", "ce doc ",
    "ce pdf", "ces pdf", "ce word", "cet excel", "ce excel", "ce tableur",
    "ce classeur", "ce csv", "cette presentation", "ce powerpoint", "ce ppt",
    "cette image", "cette photo", "ces images", "ces photos",
    "piece jointe", "pieces jointes", "fichier joint", "fichiers joints",
    "document joint", "ci-joint", "ci joint", "mon fichier", "mon document",
    "mon pdf", "mes fichiers", "mes documents",
)

#: Le mot tel qu'il est dit -> l'extension a produire.
FORMATS = {
    "pdf": "pdf", "word": "docx", "docx": "docx", "excel": "xlsx", "xlsx": "xlsx",
    "tableur": "xlsx", "csv": "csv", "texte": "txt", "txt": "txt",
    "powerpoint": "pptx", "pptx": "pptx", "png": "png", "jpg": "jpg",
    "jpeg": "jpg", "webp": "webp", "markdown": "md", "md": "md",
}

_CIBLE = re.compile(
    r"\b(?:en|au format|vers|format)\s+(?:un\s+|une\s+|fichier\s+|document\s+|image\s+)?"
    r"(" + "|".join(sorted(FORMATS, key=len, reverse=True)) + r")\b")


def _normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte or "")
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return " ".join(sans_accents.lower().replace("’", "'").split()) + " "


def format_de_conversion(phrase: str) -> Optional[str]:
    """L'extension demandee pour convertir un fichier fourni, ou None si la
    phrase ne demande pas cela."""
    texte = _normaliser(phrase)
    if not any(verbe in texte for verbe in VERBES):
        return None
    if not any(reference in texte for reference in REFERENCES_A_UN_FICHIER):
        return None
    cible = _CIBLE.search(texte)
    return FORMATS[cible.group(1)] if cible else None
