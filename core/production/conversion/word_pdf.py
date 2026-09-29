"""Word -> PDF sans LibreOffice : la structure du document, rendue par WeasyPrint.

`docx -> pdf` n'avait qu'un moteur, LibreOffice (DEC-0173). Sur une machine
qui ne l'a pas, « fais un PDF de ce Word » echouait. WeasyPrint, lui, ecrit
deja les PDF de `rediger`.

Ce moteur lit le Word avec python-docx, dans l'ordre du document, et en fait
une page HTML : titres, paragraphes, listes, tableaux, gras, italique,
souligne. Il passe APRES LibreOffice, qui garde la mise en page exacte
(polices, marges, images, en-tetes).

**Rien du document n'est interprete comme du code.** Chaque texte est
echappe (`html.escape`) : un Word qui contient « <img src=http://...> »
l'affiche, il ne le charge pas. Et WeasyPrint recoit un recuperateur d'URL
qui refuse tout — ce HTML n'en contient aucune, et n'en suivra aucune.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import List, Optional

from core.production.conversion.moteurs import MoteurEchec

STYLE = """
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 11pt; line-height: 1.4; }
h1 { font-size: 20pt; } h2 { font-size: 16pt; } h3 { font-size: 13pt; }
table { border-collapse: collapse; margin: 8pt 0; }
td, th { border: 1px solid #888; padding: 3pt 6pt; vertical-align: top; }
"""

_NIVEAU = re.compile(r"(\d+)$")


def _niveau_de_titre(nom_de_style: str) -> Optional[int]:
    """« Heading 2 » (ou « Titre 2 » d'un Word francais) -> 2 ; « Title » -> 1."""
    nom = (nom_de_style or "").strip()
    if nom in ("Title", "Titre"):
        return 1
    if nom.startswith(("Heading", "Titre")):
        trouve = _NIVEAU.search(nom)
        if trouve:
            return min(int(trouve.group(1)), 6)
    return None


def _genre_de_liste(paragraphe) -> Optional[str]:
    """`ol`, `ul`, ou None. Le style dit la nature de la liste ; une
    numerotation posee a la main sans style de liste devient une puce."""
    nom = paragraphe.style.name if paragraphe.style is not None else ""
    if nom.startswith("List Number"):
        return "ol"
    if nom.startswith("List Bullet"):
        return "ul"
    proprietes = paragraphe._p.pPr
    if proprietes is not None and proprietes.numPr is not None:
        return "ul"
    return None


def _contenu(paragraphe) -> str:
    """Le texte d'un paragraphe, echappe, avec son gras, italique, souligne."""
    morceaux: List[str] = []
    for run in paragraphe.runs:
        texte = html.escape(run.text)
        if not texte:
            continue
        if run.bold:
            texte = f"<strong>{texte}</strong>"
        if run.italic:
            texte = f"<em>{texte}</em>"
        if run.underline:
            texte = f"<u>{texte}</u>"
        morceaux.append(texte)
    return "".join(morceaux)


def _tableau(tableau) -> str:
    lignes = []
    for ligne in tableau.rows:
        cellules = "".join(
            f"<td>{'<br>'.join(_contenu(p) for p in cellule.paragraphs if p.text.strip())}</td>"
            for cellule in ligne.cells)
        lignes.append(f"<tr>{cellules}</tr>")
    return f"<table>{''.join(lignes)}</table>"


def docx_vers_html(entree: Path) -> str:
    """Le document Word, dans l'ordre, en une page HTML complete."""
    from docx import Document
    from docx.table import Table

    try:
        document = Document(str(entree))
    except Exception as erreur:  # noqa: BLE001 — un docx corrompu leve des types varies
        raise MoteurEchec(f"document Word illisible : {erreur}") from erreur

    corps: List[str] = []
    liste_ouverte: Optional[str] = None
    for bloc in document.iter_inner_content():
        genre = None if isinstance(bloc, Table) else _genre_de_liste(bloc)
        if liste_ouverte and genre != liste_ouverte:
            corps.append(f"</{liste_ouverte}>")
            liste_ouverte = None
        if isinstance(bloc, Table):
            corps.append(_tableau(bloc))
            continue
        contenu = _contenu(bloc)
        if not contenu.strip():
            continue
        if genre:
            if liste_ouverte is None:
                corps.append(f"<{genre}>")
                liste_ouverte = genre
            corps.append(f"<li>{contenu}</li>")
            continue
        niveau = _niveau_de_titre(bloc.style.name if bloc.style is not None else "")
        corps.append(f"<h{niveau}>{contenu}</h{niveau}>" if niveau else f"<p>{contenu}</p>")
    if liste_ouverte:
        corps.append(f"</{liste_ouverte}>")
    if not corps:
        raise MoteurEchec("le document Word ne contient aucun texte")
    return (f"<html><head><meta charset='utf-8'><style>{STYLE}</style></head>"
            f"<body>{''.join(corps)}</body></html>")


def _refuser_toute_url(url: str, *args, **kwargs):
    """Aucune ressource n'est chargee pendant le rendu — ni reseau, ni disque."""
    raise ValueError(f"ressource refusee pendant le rendu : {url}")


def rendre_pdf(page: str, sortie: Path) -> None:
    """Une page HTML deja echappee -> PDF, sans charger aucune ressource.
    Partage avec le tableur -> PDF (DEC-0174) : une seule facon sure de rendre."""
    import weasyprint

    try:
        weasyprint.HTML(string=page, url_fetcher=_refuser_toute_url).write_pdf(str(sortie))
    except Exception as erreur:  # noqa: BLE001 — un rendu invalide leve des types varies
        raise MoteurEchec(f"rendu PDF impossible : {erreur}") from erreur


def docx_vers_pdf(entree: Path, sortie: Path) -> None:
    rendre_pdf(docx_vers_html(entree), sortie)
