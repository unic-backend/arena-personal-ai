"""Les moteurs réels — chacun mesuré dans ce conteneur le 08/09/2026, pas
supposé installé parce qu'un paquet pip le déclare en dépendance.

Chaque fonction `convertir_xxx(entree, sortie)` fait le travail ou lève
`MoteurEchec` avec une raison lisible ; elle n'écrit jamais un `sortie`
partiel sans lever. La preuve que la sortie est un fichier RÉEL et
décodable vient d'ailleurs (`validation.py`) — un moteur qui rend sans
lever n'a encore rien prouvé.

**Aucun code de File_Converter_Pro (GPLv3) n'entre ici** — voir
`docs/audits/file_converter_pro_audit.md`, §Licence. Chaque moteur est une
implémentation neuve d'ARENA contre une bibliothèque ou un binaire externe,
au même titre que `core/connectors/ifc_generation.py` contre IfcOpenShell.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("usman.production.conversion.moteurs")

#: Au-delà, un moteur externe est considéré bloqué plutôt qu'attendu — une
#: conversion locale ne doit jamais faire pendre tout un travail de fond.
DELAI_SECONDES = 120.0


class MoteurEchec(Exception):
    """Une conversion a échoué pour une raison attendue — pas un bug d'ARENA."""


# --- LibreOffice (docx/pptx/xlsx/odt/rtf <-> pdf) --------------------------------

#: `soffice` importe un PDF comme dessin par défaut (filtre `draw_pdf_import`) ;
#: seul CE filtre explicite le fait entrer dans Writer, texte éditable. Mesuré
#: le 08/09/2026 : sans lui, la conversion PDF->DOCX rend `Error: no export
#: filter for ... docx found` et n'écrit rien, alors que le process rend 0.
FILTRE_IMPORT_PDF = "writer_pdf_import"

#: Format cible -> extension attendue de soffice. `docx`/`xlsx`/`pptx` sont
#: acceptés tels quels par `--convert-to` (filtre Office Open XML par défaut).
_EXTENSIONS_OFFICE_SOURCE = frozenset({
    "docx", "doc", "odt", "rtf", "pptx", "ppt", "odp", "xlsx", "xls", "ods",
})


def soffice_disponible() -> Tuple[bool, str]:
    chemin = shutil.which("soffice") or shutil.which("libreoffice")
    if not chemin:
        return False, "aucun binaire « soffice » ou « libreoffice » trouvé sur le PATH"
    return True, chemin


def convertir_office(entree: Path, sortie: Path, format_source: str) -> None:
    """DOCX/PPTX/XLSX/ODT/RTF -> PDF, ou PDF -> DOCX, via LibreOffice headless.

    `soffice` écrit toujours dans un dossier, avec le nom de base de
    l'entrée : on lui donne un dossier de travail jetable, puis on déplace
    le fichier produit vers `sortie` (déjà le nom final choisi par le
    connecteur — jamais celui de l'appelant).
    """
    disponible, info = soffice_disponible()
    if not disponible:
        raise MoteurEchec(info)

    format_cible = sortie.suffix.lstrip(".").lower()
    with tempfile.TemporaryDirectory(prefix="arena-conv-lo-") as travail:
        travail_p = Path(travail)
        profil = travail_p / "profil"
        sortie_dir = travail_p / "sortie"
        sortie_dir.mkdir()

        commande = [
            info, "--headless", "--norestore",
            f"-env:UserInstallation=file://{profil}",
        ]
        if format_source == "pdf":
            # Un seul jeton `--infilter=X` : mesuré le 08/09/2026, soffice
            # refuse la forme en deux arguments (`--infilter X`) avec
            # `Error in option: --infilter`, contrairement a `--convert-to`.
            commande += [f"--infilter={FILTRE_IMPORT_PDF}"]
        commande += ["--convert-to", format_cible, "--outdir", str(sortie_dir), str(entree)]

        try:
            resultat = subprocess.run(
                commande, capture_output=True, text=True, timeout=DELAI_SECONDES)
        except subprocess.TimeoutExpired:
            raise MoteurEchec(f"LibreOffice n'a pas répondu en {DELAI_SECONDES:.0f} s") from None

        produit = sortie_dir / f"{entree.stem}.{format_cible}"
        if not produit.is_file():
            detail = (resultat.stderr or resultat.stdout or "aucune sortie").strip()
            raise MoteurEchec(f"LibreOffice n'a rien écrit : {detail[:300]}")

        shutil.move(str(produit), str(sortie))


# --- Pillow (images) ----------------------------------------------------------

_FORMATS_PILLOW = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP",
                   "bmp": "BMP", "tiff": "TIFF", "gif": "GIF"}


def pillow_disponible() -> Tuple[bool, str]:
    try:
        import PIL  # noqa: F401
    except ImportError as erreur:
        return False, f"Pillow n'est pas installé : {erreur}"
    return True, "Pillow installé"


def convertir_image(entree: Path, sortie: Path) -> None:
    from PIL import Image, UnidentifiedImageError

    format_cible = _FORMATS_PILLOW.get(sortie.suffix.lstrip(".").lower())
    if format_cible is None:
        raise MoteurEchec(f"format d'image cible non pris en charge : {sortie.suffix}")

    try:
        with Image.open(entree) as img:
            # JPEG/BMP n'ont pas de canal alpha : une image RGBA y perdrait sa
            # transparence en silence si on ne la fond pas d'abord sur du blanc.
            if format_cible in ("JPEG", "BMP") and img.mode in ("RGBA", "LA", "P"):
                fond = Image.new("RGB", img.size, (255, 255, 255))
                image_rgba = img.convert("RGBA")
                fond.paste(image_rgba, mask=image_rgba.split()[-1])
                fond.save(sortie, format_cible)
            else:
                img.convert("RGB" if format_cible in ("JPEG", "BMP") else img.mode) \
                   .save(sortie, format_cible)
    except UnidentifiedImageError as erreur:
        raise MoteurEchec(f"image source illisible : {erreur}") from erreur
    except OSError as erreur:
        raise MoteurEchec(f"écriture de l'image impossible : {erreur}") from erreur


# --- CairoSVG (SVG -> PNG/PDF) --------------------------------------------------

def cairosvg_disponible() -> Tuple[bool, str]:
    try:
        import cairosvg  # noqa: F401
    except (ImportError, OSError) as erreur:
        # OSError : la bibliothèque cairo systeme (libcairo) peut manquer
        # meme quand le paquet pip est installe — mesure a faire la ou ca
        # tourne, jamais supposee depuis ce conteneur.
        return False, f"CairoSVG indisponible : {erreur}"
    return True, "CairoSVG installé"


def convertir_svg(entree: Path, sortie: Path) -> None:
    import cairosvg

    format_cible = sortie.suffix.lstrip(".").lower()
    try:
        if format_cible == "png":
            cairosvg.svg2png(url=str(entree), write_to=str(sortie))
        elif format_cible == "pdf":
            cairosvg.svg2pdf(url=str(entree), write_to=str(sortie))
        else:
            raise MoteurEchec(f"CairoSVG ne rend pas de « .{format_cible} »")
    except Exception as erreur:  # noqa: BLE001 — un SVG malformé leve un type prive a cairosvg
        if isinstance(erreur, MoteurEchec):
            raise
        raise MoteurEchec(f"SVG source illisible ou invalide : {erreur}") from erreur


# --- WeasyPrint + Markdown (HTML/Markdown/TXT -> PDF) --------------------------

def weasyprint_disponible() -> Tuple[bool, str]:
    try:
        import weasyprint  # noqa: F401
    except OSError as erreur:
        # Cause la plus frequente : pango/cairo systeme absents. Le paquet
        # pip s'installe quand meme ; c'est l'import qui echoue.
        return False, f"WeasyPrint indisponible (bibliotheques systeme manquantes ?) : {erreur}"
    except ImportError as erreur:
        return False, f"WeasyPrint n'est pas installé : {erreur}"
    return True, "WeasyPrint installé"


def convertir_document_vers_pdf(entree: Path, sortie: Path, format_source: str) -> None:
    import weasyprint

    texte = entree.read_text(encoding="utf-8", errors="replace")

    if format_source == "html":
        html = texte
    elif format_source == "md":
        import markdown as md_lib
        corps = md_lib.markdown(texte, extensions=["tables", "fenced_code"])
        html = f"<html><meta charset='utf-8'><body>{corps}</body></html>"
    elif format_source == "txt":
        echappe = (texte.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        html = (f"<html><meta charset='utf-8'><body>"
                f"<pre style='white-space:pre-wrap;font-family:monospace'>{echappe}</pre>"
                f"</body></html>")
    else:
        raise MoteurEchec(f"WeasyPrint : format source non pris en charge « {format_source} »")

    try:
        weasyprint.HTML(string=html, base_url=str(entree.parent)).write_pdf(str(sortie))
    except Exception as erreur:  # noqa: BLE001 — un HTML/CSS invalide leve des types varies
        raise MoteurEchec(f"rendu PDF impossible : {erreur}") from erreur


# --- pypdfium2 (PDF -> image, déjà une dépendance d'ARENA — tools/documents/reader.py)

def pypdfium2_disponible() -> Tuple[bool, str]:
    try:
        import pypdfium2  # noqa: F401
    except ImportError as erreur:
        return False, f"pypdfium2 n'est pas installé : {erreur}"
    return True, "pypdfium2 installé"


def convertir_pdf_vers_image(entree: Path, sortie: Path, page: int = 0) -> None:
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(str(entree))
    except Exception as erreur:  # noqa: BLE001 — pdfium leve des erreurs C opaques
        raise MoteurEchec(f"PDF source illisible : {erreur}") from erreur

    try:
        if page >= len(document):
            raise MoteurEchec(f"le PDF n'a que {len(document)} page(s), page {page} demandée")
        bitmap = document[page].render(scale=2.0)
        image = bitmap.to_pil()
        format_cible = sortie.suffix.lstrip(".").upper()
        image.convert("RGB").save(sortie, "JPEG" if format_cible in ("JPG", "JPEG") else format_cible)
    finally:
        document.close()


# --- FFmpeg (audio/vidéo) — jamais un second moteur : voir tools/video/ffmpeg_tool.py

def ffmpeg_disponible() -> Tuple[bool, str]:
    from tools.video.ffmpeg_tool import FFmpegTool
    outil = FFmpegTool()
    if not outil.is_available():
        return False, f"ffmpeg introuvable ou ne répond pas ({outil.get_executable()})"
    return True, outil.get_executable()


def convertir_audio_video(entree: Path, sortie: Path) -> None:
    from tools.video.ffmpeg_tool import FFmpegTool

    outil = FFmpegTool()
    ok, raison = outil.convertir(str(entree), str(sortie), timeout=DELAI_SECONDES)
    if not ok:
        raise MoteurEchec(raison)


# --- ZIP (stdlib, aucune dépendance nouvelle) -----------------------------------

def zip_disponible() -> Tuple[bool, str]:
    return True, "zipfile (bibliothèque standard)"


def compresser_zip(entrees: List[Path], sortie: Path) -> None:
    import zipfile

    from core.production.conversion.securite import noms_zip

    raison = noms_zip(entrees)
    if raison:
        raise MoteurEchec(raison)

    try:
        with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as zf:
            for chemin in entrees:
                zf.write(chemin, arcname=chemin.name)
    except OSError as erreur:
        raise MoteurEchec(f"écriture de l'archive impossible : {erreur}") from erreur


def extraire_zip(archive: Path, dossier_cible: Path) -> List[Path]:
    import zipfile

    from core.production.conversion.securite import extraction_zip_sure

    dossier_cible.mkdir(parents=True, exist_ok=True)
    raison = extraction_zip_sure(archive, dossier_cible)
    if raison:
        raise MoteurEchec(raison)

    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dossier_cible)
        return [dossier_cible / info.filename for info in zf.infolist()
                if not info.filename.endswith("/")]
