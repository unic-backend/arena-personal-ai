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

from core.production.conversion import moteurs as m

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
