"""CSV <-> Excel : les tableaux qu'on s'echange, sans LibreOffice.

La consigne JARVIS (DEC-0163) cite « file transformation » et « spreadsheet
generation ». Jusqu'au 29/09/2026, la matrice de conversion ne connaissait
aucun couple CSV : « transforme ce CSV en Excel » n'avait aucun moteur, alors
qu'`openpyxl` est installe et que le module `csv` est dans Python.

Deux moteurs (DEC-0169) :

- **CSV -> XLSX.** Le separateur (`;` d'un Excel francais, `,`, tabulation,
  `|`) et l'encodage (UTF-8, ou Windows-1252 d'un vieil export) sont
  reconnus. Les nombres deviennent des nombres selon les regles d'`en_nombre`
  (« 1 250,50 » -> 1250.5 ; « 00221 » reste un texte). Une premiere ligne
  sans aucun nombre passe en gras : c'est un en-tete.
- **XLSX -> CSV.** La feuille active, au format qu'un Excel francais rouvre
  sans assistant : `;`, virgule decimale, UTF-8 avec BOM.

**Aucune formule ne traverse, dans aucun sens.** Un texte commencant par
« = » reste un texte dans le classeur (comme `bureautique.ecrire_case`) ; dans le CSV, un texte
qui commence par `=`, `+`, `-` ou `@` est precede d'une apostrophe, ce qui
empeche un tableur de l'executer a l'ouverture (injection CSV).
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time
from itertools import chain, islice
from pathlib import Path
from typing import Iterator, List

from core.production.conversion.bureautique import _nom_de_feuille, en_nombre, lire_blocs, sans_emphase
from core.production.conversion.moteurs import MoteurEchec

#: Les separateurs essayes, dans l'ordre de preference en cas d'egalite : le
#: point-virgule d'abord, parce qu'une virgule decimale ne le trahit jamais.
SEPARATEURS = ";,\t|"

#: Ce qu'un tableur interprete comme le debut d'une formule.
DEBUTS_DE_FORMULE = ("=", "+", "-", "@", "\t", "\r")


def lire_texte(entree: Path) -> str:
    """Le contenu du CSV : UTF-8 (BOM compris) d'abord, Windows-1252 sinon —
    l'encodage d'un export Excel francais ancien. Jamais de caractere avale
    en silence : un octet que ni l'un ni l'autre ne lit fait echouer."""
    brut = entree.read_bytes()
    try:
        return brut.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Pas de l'UTF-8 : on essaie l'encodage d'un vieil export, qui dit
        # a son tour s'il echoue.
        return _en_windows_1252(brut)


def _en_windows_1252(brut: bytes) -> str:
    try:
        return brut.decode("cp1252")
    except UnicodeDecodeError as erreur:
        raise MoteurEchec(f"encodage du CSV illisible (ni UTF-8 ni Windows-1252) : {erreur}") from erreur


def separateur(texte: str) -> str:
    """Le separateur de ce CSV. `csv.Sniffer` sur un extrait, et a defaut le
    caractere le plus frequent de la premiere ligne."""
    extrait = texte[:20000]
    try:
        return csv.Sniffer().sniff(extrait, delimiters=SEPARATEURS).delimiter
    except csv.Error:
        premiere = extrait.splitlines()[0] if extrait.splitlines() else ""
        comptes = {s: premiere.count(s) for s in SEPARATEURS}
        meilleur = max(SEPARATEURS, key=lambda s: comptes[s])
        return meilleur if comptes[meilleur] else ","


#: Ce qu'une feuille Excel peut tenir. Au-dela, le fichier serait tronque par
#: le tableur a l'ouverture — on refuse plutot que de livrer un classeur faux.
LIGNES_MAX = 1_048_576
COLONNES_MAX = 16_384

#: Les largeurs de colonne se mesurent sur ce debut de fichier : un CSV de
#: plusieurs centaines de Mo ne se garde pas entier en memoire pour ca.
LIGNES_POUR_LES_LARGEURS = 200


def lire_lignes(texte: str) -> Iterator[List[str]]:
    """Les lignes non vides du CSV, une par une."""
    for ligne in csv.reader(io.StringIO(texte), delimiter=separateur(texte)):
        if any(cellule.strip() for cellule in ligne):
            yield ligne


def csv_vers_xlsx(entree: Path, sortie: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    lignes = lire_lignes(lire_texte(entree))
    debut = list(islice(lignes, LIGNES_POUR_LES_LARGEURS))
    if not debut:
        raise MoteurEchec("le CSV ne contient aucune ligne")
    en_tete = all(en_nombre(cellule) is None for cellule in debut[0])

    # Ecriture en flux (`write_only`) : la memoire ne grossit pas avec le fichier.
    classeur = Workbook(write_only=True)
    feuille = classeur.create_sheet(_nom_de_feuille(entree.stem, set()))
    largeurs: dict = {}
    for ligne in debut:
        for colonne, cellule in enumerate(ligne, start=1):
            largeurs[colonne] = max(largeurs.get(colonne, 0), len(cellule))
    for colonne, largeur in largeurs.items():
        if colonne <= COLONNES_MAX:
            feuille.column_dimensions[get_column_letter(colonne)].width = min(max(10, largeur + 2), 60)
    if en_tete:
        feuille.freeze_panes = "A2"

    ecrites = 0
    try:
        for ligne in chain(debut, lignes):
            ecrites += 1
            if ecrites > LIGNES_MAX:
                raise MoteurEchec(f"plus de {LIGNES_MAX} lignes : une feuille Excel ne les tient pas")
            if len(ligne) > COLONNES_MAX:
                raise MoteurEchec(f"plus de {COLONNES_MAX} colonnes : une feuille Excel ne les tient pas")
            titre = en_tete and ecrites == 1
            cases = []
            for cellule in ligne:
                nombre = None if titre else en_nombre(cellule)
                case = WriteOnlyCell(feuille, value=nombre if nombre is not None else cellule)
                if nombre is None:
                    # Un texte reste un texte : jamais une formule (voir `ecrire_case`).
                    case.data_type = "s"
                if titre:
                    case.font = Font(bold=True)
                cases.append(case)
            feuille.append(cases)
    except BaseException:
        # Refermer le flux en cours d'ecriture : sans ca, openpyxl laisse un
        # generateur ouvert qui leve a sa destruction (mesure le 29/09/2026).
        feuille.close()
        raise
    classeur.save(str(sortie))


def _en_texte(valeur: object) -> str:
    """Une case du classeur, ecrite comme un Excel francais la relit."""
    if valeur is None:
        return ""
    if isinstance(valeur, bool):
        return "VRAI" if valeur else "FAUX"
    if isinstance(valeur, (int, float)):
        texte = repr(valeur) if isinstance(valeur, float) else str(valeur)
        if texte.endswith(".0"):
            texte = texte[:-2]
        return texte.replace(".", ",")
    if isinstance(valeur, datetime):
        return valeur.strftime("%d/%m/%Y %H:%M") if valeur.time() != time(0) else valeur.strftime("%d/%m/%Y")
    if isinstance(valeur, date):
        return valeur.strftime("%d/%m/%Y")
    texte = str(valeur)
    if texte.startswith(DEBUTS_DE_FORMULE):
        # Neutralise : l'apostrophe fait lire la case comme du texte.
        return "'" + texte
    return texte


def xlsx_vers_csv(entree: Path, sortie: Path) -> None:
    from openpyxl import load_workbook

    try:
        # `data_only` : la VALEUR d'une formule, telle qu'Excel l'a calculee
        # et gardee — jamais la formule elle-meme.
        classeur = load_workbook(str(entree), read_only=True, data_only=True)
    except Exception as erreur:  # noqa: BLE001 — un classeur illisible est un echec du moteur
        raise MoteurEchec(f"classeur illisible : {erreur}") from erreur
    try:
        feuille = classeur.active
        lignes: List[List[str]] = []
        for rangee in feuille.iter_rows(values_only=True):
            cellules = [_en_texte(v) for v in rangee]
            while cellules and not cellules[-1]:
                cellules.pop()
            lignes.append(cellules)
    finally:
        classeur.close()
    while lignes and not lignes[-1]:
        lignes.pop()
    if not lignes:
        raise MoteurEchec("la feuille active est vide")
    with sortie.open("w", encoding="utf-8-sig", newline="") as fichier:
        csv.writer(fichier, delimiter=";", lineterminator="\r\n").writerows(lignes)


def markdown_vers_csv(entree: Path, sortie: Path) -> None:
    """Le premier tableau d'une reponse, en CSV (DEC-0171).

    « Fais-moi un CSV de ce tableau » : le modele repond en markdown, et un
    CSV ne tient qu'UN tableau. Le premier est ecrit ; s'il y en a d'autres,
    la limite de qualite le dit. Sans aucun tableau, le moteur refuse — un
    CSV d'une colonne de phrases ne serait pas ce qui a ete demande.

    Meme format que `xlsx_vers_csv` : `;`, virgule decimale, UTF-8 avec BOM,
    et un texte qui ressemble a une formule est neutralise.
    """
    blocs = lire_blocs(entree.read_text(encoding="utf-8", errors="replace"))
    tableau = next((b for b in blocs if b.genre == "tableau" and b.lignes), None)
    if tableau is None:
        raise MoteurEchec("aucun tableau dans le texte : un CSV est un tableau")
    lignes = []
    for numero, ligne in enumerate(tableau.lignes):
        cellules = []
        for cellule in ligne:
            nue = sans_emphase(cellule)
            nombre = None if numero == 0 else en_nombre(nue)
            cellules.append(_en_texte(nombre if nombre is not None else nue))
        lignes.append(cellules)
    with sortie.open("w", encoding="utf-8-sig", newline="") as fichier:
        csv.writer(fichier, delimiter=";", lineterminator="\r\n").writerows(lignes)


# --- Excel -> PDF sans LibreOffice (DEC-0174) ----------------------------------------

#: Au-dela, un PDF n'est plus lisible — et son rendu prendrait des minutes.
#: Le moteur refuse et dit quoi faire, plutot que de tronquer en silence.
LIGNES_PDF_MAX = 5000

STYLE_TABLEUR = """
@page { size: A4 landscape; margin: 12mm; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 9pt; }
h2 { font-size: 12pt; margin: 10pt 0 4pt; }
table { border-collapse: collapse; }
td, th { border: 1px solid #999; padding: 2pt 5pt; vertical-align: top; }
th { background: #eee; text-align: left; }
td.nombre { text-align: right; }
"""


def _affichee(valeur: object) -> str:
    """Une case telle qu'un tableur francais l'affiche. Un texte reste le
    texte, sans l'apostrophe du CSV : un PDF n'execute rien."""
    if isinstance(valeur, str):
        return valeur
    return _en_texte(valeur)


def _case(balise: str, valeur: object) -> str:
    """Une case du tableau HTML, echappee ; un nombre s'aligne a droite."""
    import html

    nombre = isinstance(valeur, (int, float)) and not isinstance(valeur, bool)
    classe = ' class="nombre"' if nombre else ""
    return f"<{balise}{classe}>{html.escape(_affichee(valeur))}</{balise}>"


def xlsx_vers_html(entree: Path) -> str:
    """Chaque feuille non vide : son nom, puis son tableau. Tout est echappe."""
    import html

    from openpyxl import load_workbook

    try:
        classeur = load_workbook(str(entree), read_only=True, data_only=True)
    except Exception as erreur:  # noqa: BLE001 — un classeur illisible est un echec du moteur
        raise MoteurEchec(f"classeur illisible : {erreur}") from erreur
    corps: List[str] = []
    total = 0
    try:
        for feuille in classeur.worksheets:
            lignes = []
            for rangee in feuille.iter_rows(values_only=True):
                valeurs = list(rangee)
                while valeurs and valeurs[-1] in (None, ""):
                    valeurs.pop()
                if valeurs:
                    lignes.append(valeurs)
            if not lignes:
                continue
            total += len(lignes)
            if total > LIGNES_PDF_MAX:
                raise MoteurEchec(
                    f"plus de {LIGNES_PDF_MAX} lignes : trop grand pour un PDF lisible "
                    f"— convertis ce classeur en CSV")
            largeur = max(len(v) for v in lignes)
            en_tete = all(isinstance(v, str) or v is None for v in lignes[0]) and len(lignes) > 1
            rangs = []
            for numero, valeurs in enumerate(lignes):
                valeurs = valeurs + [None] * (largeur - len(valeurs))
                balise = "th" if en_tete and numero == 0 else "td"
                cases = "".join(_case(balise, v) for v in valeurs)
                rangs.append(f"<tr>{cases}</tr>")
            corps.append(f"<h2>{html.escape(feuille.title)}</h2><table>{''.join(rangs)}</table>")
    finally:
        classeur.close()
    if not corps:
        raise MoteurEchec("le classeur ne contient aucune donnee")
    return (f"<html><head><meta charset='utf-8'><style>{STYLE_TABLEUR}</style></head>"
            f"<body>{''.join(corps)}</body></html>")


def xlsx_vers_pdf(entree: Path, sortie: Path) -> None:
    from core.production.conversion.word_pdf import rendre_pdf

    rendre_pdf(xlsx_vers_html(entree), sortie)
