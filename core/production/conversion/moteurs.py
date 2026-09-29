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
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

#: Même piège, côté HTML. Mesuré le 20/09/2026 sur cette machine :
#: `soffice --convert-to docx page.html` répond « Error: no export filter for
#: ... docx found, aborting » et n'écrit rien. Il faut **les deux** filtres
#: nommés — l'import, sinon le HTML entre dans Writer/Web qui n'exporte pas
#: DOCX, et l'export, que `--convert-to docx` seul ne suffit pas à désigner
#: depuis ce module d'import-là. Avec les deux : 5274 octets de DOCX réel.
FILTRE_IMPORT_HTML = "HTML (StarWriter)"

#: Le filtre d'export à nommer explicitement, par format cible, **et
#: seulement pour une source HTML** : les couples déjà en service
#: (`docx -> pdf`, `pdf -> docx`…) marchent avec `--convert-to <ext>` depuis
#: le 08/09/2026, et rien ne justifie de changer ce qui est mesuré bon.
FILTRES_EXPORT_DEPUIS_HTML = {"docx": "docx:MS Word 2007 XML"}

#: Format cible -> extension attendue de soffice. `docx`/`xlsx`/`pptx` sont
#: acceptés tels quels par `--convert-to` (filtre Office Open XML par défaut).
_EXTENSIONS_OFFICE_SOURCE = frozenset({
    "docx", "doc", "odt", "rtf", "pptx", "ppt", "odp", "xlsx", "xls", "ods",
})


#: Une conversion d'essai qui depasse ce delai compte comme un echec. Le
#: premier demarrage de LibreOffice est lent (profil a creer) : large expres.
DELAI_SONDE_SECONDES = 90.0

#: Duree de validite d'une sonde. Une reussite vaut dix minutes ; un echec
#: une seule, pour qu'un LibreOffice installe ou repare soit vu vite.
VALIDITE_SONDE_OK = 600.0
VALIDITE_SONDE_KO = 60.0

_sondes_soffice: Dict[str, Tuple[float, bool, str]] = {}
_verrou_sonde = threading.Lock()


def _binaire_soffice() -> Optional[str]:
    return shutil.which("soffice") or shutil.which("libreoffice")


def _maintenant() -> float:
    return time.monotonic()


def oublier_sonde_soffice() -> None:
    """Oublie les sondes gardees — la suivante reconvertit pour de vrai."""
    with _verrou_sonde:
        _sondes_soffice.clear()


def _sonder_soffice(chemin: str) -> Tuple[bool, str]:
    """Une vraie conversion d'essai : un texte d'une ligne -> PDF.

    Mesure du 29/09/2026 : dans le conteneur de travail, `soffice` existe,
    repond a `--version`, et rend 0 a une conversion **sans rien ecrire**
    (« source file could not be loaded »). Verifier la presence du binaire
    annoncait disponible un moteur qui ne convertit rien. Seul un fichier
    produit, et qui commence comme un PDF, prouve qu'il marche.
    """
    with tempfile.TemporaryDirectory(prefix="arena-sonde-lo-") as travail:
        travail_p = Path(travail)
        entree = travail_p / "sonde.txt"
        entree.write_text("ARENA : conversion d'essai.\n", encoding="utf-8")
        sortie_dir = travail_p / "sortie"
        sortie_dir.mkdir()
        commande = [
            chemin, "--headless", "--norestore",
            f"-env:UserInstallation=file://{travail_p / 'profil'}",
            "--convert-to", "pdf", "--outdir", str(sortie_dir), str(entree),
        ]
        try:
            resultat = subprocess.run(
                commande, capture_output=True, text=True, timeout=DELAI_SONDE_SECONDES)
        except subprocess.TimeoutExpired:
            return False, (f"LibreOffice présent ({chemin}) mais sa conversion d'essai "
                           f"n'a pas abouti en {DELAI_SONDE_SECONDES:.0f} s")
        except OSError as erreur:
            return False, f"LibreOffice présent ({chemin}) mais ne se lance pas : {erreur}"
        produit = sortie_dir / "sonde.pdf"
        if produit.is_file() and produit.read_bytes()[:5] == b"%PDF-":
            return True, f"{chemin} (conversion d'essai réussie)"
        detail = (resultat.stderr or resultat.stdout or "aucune sortie").strip()
        return False, (f"LibreOffice présent ({chemin}) mais sa conversion d'essai "
                       f"n'a rien produit : {detail[:300]}")


def soffice_disponible() -> Tuple[bool, str]:
    """LibreOffice est-il utilisable, mesure par une vraie conversion ?

    Le resultat est garde (`VALIDITE_SONDE_OK` / `_KO`) : la matrice interroge
    cette sonde pour chaque couple LibreOffice, et le connecteur a chaque
    conversion — relancer LibreOffice a chaque fois couterait des secondes.
    """
    chemin = _binaire_soffice()
    if not chemin:
        return False, "aucun binaire « soffice » ou « libreoffice » trouvé sur le PATH"
    with _verrou_sonde:
        garde = _sondes_soffice.get(chemin)
        if garde is not None:
            instant, ok, info = garde
            validite = VALIDITE_SONDE_OK if ok else VALIDITE_SONDE_KO
            if _maintenant() - instant < validite:
                return ok, info
        ok, info = _sonder_soffice(chemin)
        _sondes_soffice[chemin] = (_maintenant(), ok, info)
    if not ok:
        logger.warning("%s", info)
    return ok, info


def _chemin_soffice_verifie() -> str:
    """Le binaire a lancer, apres la sonde. Leve `MoteurEchec` sinon."""
    disponible, info = soffice_disponible()
    if not disponible:
        raise MoteurEchec(info)
    chemin = _binaire_soffice()
    if not chemin:
        raise MoteurEchec("aucun binaire « soffice » ou « libreoffice » trouvé sur le PATH")
    return chemin


def convertir_office(entree: Path, sortie: Path, format_source: str) -> None:
    """DOCX/PPTX/XLSX/ODT/RTF -> PDF, ou PDF -> DOCX, via LibreOffice headless.

    `soffice` écrit toujours dans un dossier, avec le nom de base de
    l'entrée : on lui donne un dossier de travail jetable, puis on déplace
    le fichier produit vers `sortie` (déjà le nom final choisi par le
    connecteur — jamais celui de l'appelant).
    """
    info = _chemin_soffice_verifie()

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
        cible_arg = format_cible
        if format_source == "pdf":
            # Un seul jeton `--infilter=X` : mesuré le 08/09/2026, soffice
            # refuse la forme en deux arguments (`--infilter X`) avec
            # `Error in option: --infilter`, contrairement a `--convert-to`.
            commande += [f"--infilter={FILTRE_IMPORT_PDF}"]
        elif format_source == "html":
            commande += [f"--infilter={FILTRE_IMPORT_HTML}"]
            cible_arg = FILTRES_EXPORT_DEPUIS_HTML.get(format_cible, format_cible)
        commande += ["--convert-to", cible_arg, "--outdir", str(sortie_dir), str(entree)]

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


def texte_vers_html(texte: str, format_source: str) -> str:
    """Markdown, texte brut ou HTML -> une page HTML complète.

    Extrait de `convertir_document_vers_pdf` le 20/09/2026, parce que le
    chemin « rédiger en DOCX » a besoin exactement du même rendu avant de
    passer la main à LibreOffice. Deux implémentations du même markdown
    donneraient deux documents différents pour le même texte, selon le
    format demandé — l'écart serait invisible jusqu'au jour où il compte.

    Raises:
        MoteurEchec: si `format_source` n'est pas `html`, `md` ou `txt`.
    """
    if format_source == "html":
        return texte
    if format_source == "md":
        import markdown as md_lib
        corps = md_lib.markdown(texte, extensions=["tables", "fenced_code"])
        return f"<html><meta charset='utf-8'><body>{corps}</body></html>"
    if format_source == "txt":
        echappe = (texte.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        return (f"<html><meta charset='utf-8'><body>"
                f"<pre style='white-space:pre-wrap;font-family:monospace'>{echappe}</pre>"
                f"</body></html>")
    raise MoteurEchec(f"format source non pris en charge « {format_source} »")


def convertir_document_vers_pdf(entree: Path, sortie: Path, format_source: str) -> None:
    import weasyprint

    texte = entree.read_text(encoding="utf-8", errors="replace")
    html = texte_vers_html(texte, format_source)

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
