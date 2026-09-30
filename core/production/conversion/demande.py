"""« Convertis ce fichier en Word » : la phrase qui demande de CONVERTIR une
piece jointe, et le format voulu (DEC-0177, DEC-0200).

Trois conditions, toutes nécessaires :

1. un verbe de conversion (« convertis », « transforme », « mets », « passe »,
   « exporte », « rends », « recreate », « turn », « make ») ;
2. un format cible annoncé (« en Word », « au format PDF », « vers Excel »,
   « en DrawIO », « éditable ») ;
3. **une référence à un fichier fourni** (« ce fichier », « ce PDF », « la
   pièce jointe », « cette image », « ce diagramme », « this screenshot »).

La troisième sépare cette demande de la rédaction : « fais-moi un PDF de ça »
écrit la RÉPONSE dans un fichier (`format_de_document_demande`, chat.py) ;
« convertis ce PDF en Word » convertit le fichier ENVOYÉ. Sans elle, les deux
se confondraient.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

VERBES = (
    "convertis", "convertir", "convertit", "converti ", "conversion", "convert",
    "transforme", "transformer", "transform", "mets ", "mettre ", "passe ", "passer ",
    "exporte", "exporter", "export", "enregistre", "enregistrer",
    "rends", "rendre", "make", "turn", "recree", "recreate", "recrée",
)

REFERENCES_A_UN_FICHIER = (
    "ce fichier", "ces fichiers", "ce document", "ces documents", "ce doc",
    "ce pdf", "ces pdf", "ce word", "cet excel", "ce excel", "ce tableur",
    "ce classeur", "ce csv", "cette presentation", "ce powerpoint", "ce ppt",
    "cette image", "cette photo", "ces images", "ces photos",
    "ce diagramme", "ces diagrammes", "ce schema", "ce schéma", "ces schemas", "ces schémas",
    "ce flowchart", "ces flowcharts", "cette capture", "ce screenshot", "ces screenshots",
    "piece jointe", "pieces jointes", "fichier joint", "fichiers joints",
    "document joint", "ci-joint", "ci joint", "mon fichier", "mon document",
    "mon pdf", "mes fichiers", "mes documents",
    "this file", "this doc", "these files", "these documents",
    "this image", "this picture", "this photo", "these images", "these photos",
    "this diagram", "these diagrams", "this architecture diagram",
    "this screenshot", "these screenshots", "this flowchart", "these flowcharts",
    "the diagram", "the image", "the screenshot", "the flowchart",
    "l'image", "le diagramme", "le schema", "le schéma", "le flowchart",
)

#: Le mot tel qu'il est dit -> l'extension a produire.
FORMATS = {
    "pdf": "pdf", "word": "docx", "docx": "docx", "excel": "xlsx", "xlsx": "xlsx",
    "tableur": "xlsx", "csv": "csv", "texte": "txt", "txt": "txt",
    "powerpoint": "pptx", "pptx": "pptx", "png": "png", "jpg": "jpg",
    "jpeg": "jpg", "webp": "webp", "markdown": "md", "md": "md",
    "drawio": "drawio", "draw.io": "drawio", "draw io": "drawio",
    "diagramme editable": "drawio", "diagramme modifiable": "drawio",
    "schema editable": "drawio", "schema modifiable": "drawio",
    "editable drawio": "drawio", "editable diagram": "drawio",
    "editable flowchart": "drawio", "drawio file": "drawio",
    "fichier drawio": "drawio", "document drawio": "drawio",
    "editable": "drawio", "modifiable": "drawio",
}

_CIBLE = re.compile(
    r"\b(?:en|au format|vers|format|into|to|as|an?)\s+(?:un\s+|une\s+|fichier\s+|document\s+|image\s+|an?\s+|editable\s+)?"
    r"(" + "|".join(sorted(FORMATS, key=len, reverse=True)) + r")\b")

_DIRECT_EDITABLE = re.compile(
    r"\b(?:make|turn|rends|rendre)\b[^.!?\n]{0,60}?\b(?:editable|modifiable)\b"
)


def _normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte or "")
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return " ".join(sans_accents.lower().replace("’", "'").split()) + " "


def format_de_conversion(phrase: str) -> Optional[str]:
    """L'extension demandée pour convertir un fichier fourni, ou None si la
    phrase ne demande pas cela."""
    texte = _normaliser(phrase)
    if not any(verbe in texte for verbe in VERBES):
        return None
    if not any(reference in texte for reference in REFERENCES_A_UN_FICHIER):
        return None

    cible = _CIBLE.search(texte)
    if cible:
        format_brut = cible.group(1).strip()
        if format_brut in FORMATS:
            return FORMATS[format_brut]

    if _DIRECT_EDITABLE.search(texte):
        return "drawio"

    if "drawio" in texte or "draw.io" in texte:
        return "drawio"

    return None
