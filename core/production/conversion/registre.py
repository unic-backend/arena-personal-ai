"""Le registre : pour un couple (format source, format cible), quels moteurs
existent RÉELLEMENT, dans quel ordre les essayer, et ce qu'un appelant doit
savoir avant de faire confiance au résultat.

Mission « File_Converter_Pro » §3 : « Le registry doit connaître exactement :
source format, target format, engine, version, availability, dependencies,
platform, quality limitations, fallback, security constraints. » Ce module
est cette table — déclarative, sans magie : ajouter un moteur, c'est ajouter
une entrée ici, jamais un `if format ==` de plus dans le connecteur.

**Pas de fallback fabriqué.** Là où un seul moteur réel existe pour un
couple, la liste ne contient qu'une entrée — en inventer une seconde pour
« avoir un fallback » serait mentir sur ce que cette machine sait
réellement faire (même discipline que `core/production/disponibilite.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from core.production.conversion import bureautique as b
from core.production.conversion import extraction
from core.production.conversion import moteurs as m
from core.production.conversion import tableurs as t

ConvertisseurFn = Callable[[Path, Path], None]
DisponibiliteFn = Callable[[], Tuple[bool, str]]


@dataclass(frozen=True)
class EntreeMoteur:
    """Un moteur, pour UN couple (source, cible) précis.

    Attributes:
        moteur_id: identifiant stable — observabilité, rapport final.
        convertir: `(entree, sortie) -> None`, lève `MoteurEchec` sinon.
        disponible: sonde réelle — jamais déduite d'un `import` réussi seul
            (WeasyPrint s'importe même quand pango/cairo système manquent).
        plateforme: `"toutes"` sauf contrainte mesurée.
        limites_qualite: ce qu'un propriétaire doit savoir avant de faire
            confiance au résultat. Chaîne vide = rien de connu à signaler.
        version: version déclarée du moteur, quand elle est connue à l'avance
            (bibliothèque pip) — vide pour un binaire externe dont la version
            dépend de la machine (LibreOffice, ffmpeg).
    """

    moteur_id: str
    convertir: ConvertisseurFn
    disponible: DisponibiliteFn
    plateforme: str = "toutes"
    limites_qualite: str = ""
    version: str = ""


def _office_convertir(entree: Path, sortie: Path) -> None:
    m.convertir_office(entree, sortie, entree.suffix.lstrip(".").lower())


def _document_pdf_convertir(entree: Path, sortie: Path) -> None:
    m.convertir_document_vers_pdf(entree, sortie, entree.suffix.lstrip(".").lower())


#: (format_source, format_cible) -> moteurs, dans l'ordre à essayer.
MATRICE: Dict[Tuple[str, str], List[EntreeMoteur]] = {}


def _enregistrer(sources: List[str], cibles: List[str], entree: EntreeMoteur) -> None:
    for source in sources:
        for cible in cibles:
            MATRICE.setdefault((source, cible), []).append(entree)


# --- LibreOffice : Office -> PDF, PDF -> DOCX ------------------------------------
# Mesuré le 08/09/2026 dans ce conteneur (LibreOffice 24.2.7) : les cinq
# couples ci-dessous produisent un fichier réel, relu. Le "PDF -> DOCX"
# porte une limite de qualité mesurée, pas supposée (voir le moteur).
_enregistrer(
    ["docx", "odt", "rtf"], ["pdf"],
    EntreeMoteur("libreoffice", _office_convertir, m.soffice_disponible,
                 limites_qualite=""))
_enregistrer(
    ["pptx", "odp"], ["pdf"],
    EntreeMoteur("libreoffice", _office_convertir, m.soffice_disponible))
_enregistrer(
    ["xlsx", "ods"], ["pdf"],
    EntreeMoteur("libreoffice", _office_convertir, m.soffice_disponible))
_enregistrer(
    ["pdf"], ["docx"],
    EntreeMoteur(
        "libreoffice", _office_convertir, m.soffice_disponible,
        limites_qualite=(
            "Le texte importé atterrit dans des cadres de position fixe, "
            "pas dans un flux de paragraphes reliable comme un DOCX écrit "
            "à la main — attendu d'un import PDF, mesuré le 08/09/2026 : le "
            "texte est réel et complet, sa mise en page ne se retouche pas "
            "facilement dans Word/LibreOffice après coup.")))
# Sans LibreOffice (29/09/2026, DEC-0172) : le texte seul, dans un Word
# modifiable. APRES LibreOffice, qui garde la mise en page quand il est la.
_enregistrer(
    ["pdf"], ["docx"],
    EntreeMoteur(
        "lecteur-documents", extraction.pdf_vers_docx, b.python_docx_disponible,
        version="1.2.0",
        limites_qualite=(
            "Texte seul : ni mise en page, ni images, ni tableaux reconstruits "
            "— une ligne du PDF devient un paragraphe, un saut de page separe "
            "les pages. Une page scannee est lue par OCR et signalee, a "
            "relire.")))

# --- LibreOffice : HTML -> DOCX (20/09/2026) ---------------------------------------
# Mesuré sur cette machine avant d'être déclaré : 5274 octets de DOCX réel,
# relu par la validation. Ce couple existe pour que « écris-moi ça en Word »
# ait un chemin : `rediger` rend le markdown en HTML, LibreOffice finit le
# travail. Il sert aussi une page HTML fournie par le propriétaire.
_enregistrer(
    ["html"], ["docx"],
    EntreeMoteur(
        "libreoffice", _office_convertir, m.soffice_disponible,
        limites_qualite=(
            "Le CSS avancé (grid/flex, polices web) ne survit pas à l'import "
            "Writer : le texte, les titres et les tableaux passent, la mise "
            "en page fine non.")))

# --- Bureautique native : Markdown -> Excel, PowerPoint, Word (29/09/2026) ---------
# Les fichiers de bureau de la consigne JARVIS (DEC-0167), ecrits par des
# bibliotheques deja installees pour LIRE ces formats — aucun binaire
# systeme. Le Word natif passe AVANT LibreOffice : il marche sur une machine
# sans LibreOffice, et le chemin HTML -> DOCX reste la pour une page fournie.
_enregistrer(
    ["md"], ["xlsx"],
    EntreeMoteur(
        "openpyxl", b.markdown_vers_xlsx, b.openpyxl_disponible, version="3.1.5",
        limites_qualite=(
            "Chaque tableau markdown devient une feuille, ses nombres des "
            "nombres ; un texte sans tableau devient une colonne, une ligne "
            "par ligne. Pas de formule ni de graphique.")))
_enregistrer(
    ["md"], ["pptx"],
    EntreeMoteur(
        "python-pptx", b.markdown_vers_pptx, b.python_pptx_disponible, version="1.0.2",
        limites_qualite=(
            "Une diapositive par titre, six puces au plus (au-dela, une "
            "diapositive « suite ») ; theme par defaut, sans image ni "
            "graphique.")))
_enregistrer(
    ["md"], ["docx"],
    EntreeMoteur(
        "python-docx", b.markdown_vers_docx, b.python_docx_disponible, version="1.2.0",
        limites_qualite=(
            "Titres, paragraphes, listes, tableaux, gras et italique ; styles "
            "Word par defaut, sans image.")))

# --- Tableurs : CSV <-> Excel (29/09/2026) -----------------------------------------
# DEC-0169. Aucun couple CSV n'existait : « transforme ce CSV en Excel » n'avait
# aucun moteur. Aucune formule ne traverse, dans aucun sens (injection CSV).
_enregistrer(
    ["csv"], ["xlsx"],
    EntreeMoteur(
        "openpyxl", t.csv_vers_xlsx, b.openpyxl_disponible, version="3.1.5",
        limites_qualite=(
            "Une feuille ; separateur et encodage (UTF-8 ou Windows-1252) "
            "reconnus. Un code commencant par zero ou de plus de 15 chiffres "
            "reste du texte ; un texte commencant par « = » n'est jamais une "
            "formule.")))
_enregistrer(
    ["xlsx"], ["csv"],
    EntreeMoteur(
        "openpyxl", t.xlsx_vers_csv, b.openpyxl_disponible, version="3.1.5",
        limites_qualite=(
            "Seule la feuille active est ecrite. Format Excel francais : « ; », "
            "virgule decimale, UTF-8 avec BOM. Une formule donne la valeur "
            "qu'Excel a enregistree — vide si le classeur n'a jamais ete "
            "ouvert dans un tableur. Un texte commencant par = + - @ est "
            "precede d'une apostrophe.")))

# --- Lecteur de documents : PDF / Word / Excel / PowerPoint -> texte (29/09/2026) --
# DEC-0170. Le lecteur existait (`tools/documents/reader.py`, celui des pieces
# jointes et du RAG), mais aucune conversion vers .txt : « sors-moi le texte de
# ce PDF » n'avait pas de moteur. Chaque passage garde sa provenance, et une
# page lue par OCR le dit.
_enregistrer(
    ["pdf", "docx", "xlsx", "pptx"], ["txt"],
    EntreeMoteur(
        "lecteur-documents", extraction.document_vers_texte, extraction.disponible,
        limites_qualite=(
            "Texte seul : la mise en page, les images et les graphiques sont "
            "perdus ; un tableau devient des lignes « a | b | c ». Chaque page, "
            "feuille ou diapositive est precedee de son origine ; une page "
            "scannee est lue par OCR et marquee « (OCR) », a relire.")))

# --- Pillow : images ---------------------------------------------------------------
_FORMATS_IMAGE = ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif"]
_enregistrer(_FORMATS_IMAGE, _FORMATS_IMAGE,
             EntreeMoteur("pillow", m.convertir_image, m.pillow_disponible,
                          version="12.0.0"))

# --- CairoSVG : SVG -> PNG/PDF -----------------------------------------------------
_enregistrer(["svg"], ["png", "pdf"],
             EntreeMoteur("cairosvg", m.convertir_svg, m.cairosvg_disponible,
                          version="2.9.0"))

# --- WeasyPrint (+Markdown) : HTML/Markdown/TXT -> PDF -----------------------------
_enregistrer(["html", "md", "txt"], ["pdf"],
             EntreeMoteur("weasyprint", _document_pdf_convertir, m.weasyprint_disponible,
                          version="68.1",
                          limites_qualite="CSS moderne (grid/flex avancé) partiellement "
                                          "supporté par WeasyPrint ; suffisant pour du "
                                          "texte/tableaux simples."))

# --- pypdfium2 : PDF -> image (déjà une dépendance ARENA) --------------------------
_enregistrer(["pdf"], ["png", "jpg", "jpeg"],
             EntreeMoteur("pypdfium2", m.convertir_pdf_vers_image, m.pypdfium2_disponible,
                          version="5.13.0",
                          limites_qualite="Rend uniquement la première page."))

# --- FFmpeg : audio/vidéo -----------------------------------------------------------
_FORMATS_AUDIO = ["mp3", "wav", "flac", "aac", "ogg", "m4a"]
_FORMATS_VIDEO = ["mp4", "mkv", "mov", "avi", "webm"]
_enregistrer(_FORMATS_AUDIO, _FORMATS_AUDIO,
             EntreeMoteur("ffmpeg", m.convertir_audio_video, m.ffmpeg_disponible))
_enregistrer(_FORMATS_VIDEO, _FORMATS_VIDEO,
             EntreeMoteur("ffmpeg", m.convertir_audio_video, m.ffmpeg_disponible))
_enregistrer(_FORMATS_VIDEO, _FORMATS_AUDIO,
             EntreeMoteur("ffmpeg", m.convertir_audio_video, m.ffmpeg_disponible,
                          limites_qualite="Extrait la piste audio ; toute image est perdue."))


def moteurs_pour(format_source: str, format_cible: str) -> List[EntreeMoteur]:
    """Les moteurs déclarés pour ce couple, dans l'ordre. Liste vide si aucun."""
    return list(MATRICE.get((format_source.lower().lstrip("."), format_cible.lower().lstrip(".")), []))


def couples_connus() -> List[Tuple[str, str]]:
    return sorted(MATRICE.keys())


def matrice_disponibilite() -> List[Dict[str, object]]:
    """Chaque couple déclaré, avec CE QUI EST VRAIMENT DISPONIBLE maintenant sur
    cette machine — jamais ce que le registre espère. C'est ce que
    `formats_disponibles` du connecteur rend telle quelle.
    """
    lignes: List[Dict[str, object]] = []
    for (source, cible), entrees in sorted(MATRICE.items()):
        moteurs_info = []
        au_moins_un = False
        for entree in entrees:
            ok, info = entree.disponible()
            au_moins_un = au_moins_un or ok
            moteurs_info.append({
                "moteur": entree.moteur_id, "disponible": ok,
                "info": info, "version": entree.version,
                "plateforme": entree.plateforme,
                "limites_qualite": entree.limites_qualite,
            })
        lignes.append({
            "source": source, "cible": cible,
            "disponible": au_moins_un, "moteurs": moteurs_info,
        })
    return lignes
