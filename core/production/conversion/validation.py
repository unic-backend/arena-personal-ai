"""Un fichier de sortie n'est valide que si on l'a réellement rouvert.

Mission §8 : « Ne jamais déclarer SUCCESS simplement parce qu'un subprocess
s'est terminé avec exit code 0. » `soffice` en particulier rend 0 dans des
cas où rien n'a été écrit (mesuré le 08/09/2026, PDF→DOCX sans
`--infilter` explicite : le processus se termine proprement, le fichier
attendu n'existe jamais). La seule preuve qui compte est le fichier lui-même,
rouvert par le format qu'il prétend être.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

#: Formats sur lesquels ce module sait vraiment rouvrir et vérifier le
#: contenu, plutôt que la seule taille. Un format absent d'ici retombe sur
#: la vérification générique (existe, taille > 0) — jamais un refus, parce
#: qu'une conversion vers un format que ce module ne sait pas relire n'est
#: pas pour autant invalide.
FAMILLES_IMAGE = frozenset({"png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif"})


def _generique(sortie: Path) -> Optional[str]:
    if not sortie.is_file():
        return "aucun fichier écrit"
    if sortie.stat().st_size == 0:
        return "fichier écrit mais vide"
    return None


def _pdf(sortie: Path) -> Optional[str]:
    try:
        from pypdf import PdfReader
        lecteur = PdfReader(str(sortie))
        if len(lecteur.pages) == 0:
            return "PDF écrit sans aucune page"
    except Exception as erreur:  # noqa: BLE001 — un PDF illisible est l'échec qu'on rapporte
        return f"PDF illisible après écriture : {erreur}"
    return None


def _image(sortie: Path) -> Optional[str]:
    try:
        from PIL import Image
        with Image.open(sortie) as img:
            img.verify()
    except Exception as erreur:  # noqa: BLE001
        return f"image illisible après écriture : {erreur}"
    return None


def _docx(sortie: Path) -> Optional[str]:
    try:
        from docx import Document
        Document(str(sortie))
    except Exception as erreur:  # noqa: BLE001
        return f"DOCX illisible après écriture : {erreur}"
    return None


def _pptx(sortie: Path) -> Optional[str]:
    try:
        from pptx import Presentation
        Presentation(str(sortie))
    except Exception as erreur:  # noqa: BLE001
        return f"PPTX illisible après écriture : {erreur}"
    return None


def _xlsx(sortie: Path) -> Optional[str]:
    try:
        from openpyxl import load_workbook
        load_workbook(str(sortie), read_only=True).close()
    except Exception as erreur:  # noqa: BLE001
        return f"XLSX illisible après écriture : {erreur}"
    return None


def _audio_video(sortie: Path) -> Optional[str]:
    """`ffprobe` sur le fichier écrit : au moins un flux décodable réel,
    jamais déduit de l'extension ni du code de retour de `ffmpeg`."""
    import json
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None  # ffprobe absent : la vérification générique a déjà eu lieu

    try:
        resultat = subprocess.run(
            [ffprobe, "-v", "error", "-show_streams", "-print_format", "json", str(sortie)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "ffprobe n'a pas répondu sur le fichier écrit"

    if resultat.returncode != 0:
        return f"ffprobe refuse le fichier écrit : {resultat.stderr.strip()[:200]}"
    try:
        flux = json.loads(resultat.stdout).get("streams") or []
    except json.JSONDecodeError:
        return "ffprobe a répondu, mais sans JSON exploitable"
    if not flux:
        return "fichier écrit sans aucun flux audio/vidéo décodable"
    return None


def _zip(sortie: Path) -> Optional[str]:
    if not zipfile.is_zipfile(sortie):
        return "l'archive écrite n'est pas un ZIP valide"
    with zipfile.ZipFile(sortie) as zf:
        corrompu = zf.testzip()
        if corrompu is not None:
            return f"archive écrite mais « {corrompu} » ne s'y relit pas"
    return None


FAMILLES_AUDIO_VIDEO = frozenset({
    "mp3", "wav", "flac", "aac", "ogg", "m4a",
    "mp4", "mkv", "mov", "avi", "webm",
})

_VERIFICATEURS = {
    "pdf": _pdf,
    "docx": _docx,
    "pptx": _pptx,
    "xlsx": _xlsx,
    "zip": _zip,
    **{ext: _image for ext in FAMILLES_IMAGE},
    **{ext: _audio_video for ext in FAMILLES_AUDIO_VIDEO},
}


def verifier(sortie: Path, format_cible: str) -> Optional[str]:
    """`None` si `sortie` est un fichier réel, non vide, et décodable dans
    son format déclaré. Sinon la raison, prête pour un message d'échec.
    """
    raison = _generique(sortie)
    if raison:
        return raison

    verificateur = _VERIFICATEURS.get(format_cible.lower().lstrip("."))
    if verificateur is None:
        return None
    return verificateur(sortie)
