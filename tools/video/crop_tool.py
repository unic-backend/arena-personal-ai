import logging
import shutil
import subprocess
from pathlib import Path

from tools.video.ffmpeg_tool import FFmpegTool

logger = logging.getLogger("usman.tools.video.crop")

def _trouver_ffprobe(ffmpeg_executable: str) -> str:
    """Meme discipline que `FFmpegTool._find_ffmpeg` : `ffprobe` vit
    normalement a cote de `ffmpeg`, jamais suppose present sans verification."""
    trouve = shutil.which("ffprobe")
    if trouve:
        return trouve
    voisin = Path(ffmpeg_executable).with_name(
        "ffprobe.exe" if ffmpeg_executable.lower().endswith(".exe") else "ffprobe")
    if voisin.exists():
        return str(voisin)
    return "ffprobe"


class CropTool:
    """Outil de recadrage et de conversion vers le format vertical 9:16 (1080x1920)."""

    def __init__(self):
        self.ffmpeg = FFmpegTool()

    def _sortie_est_valide(self, output_file: Path) -> bool:
        """Le fichier existe, n'est pas vide, et `ffprobe` y lit un vrai flux
        video — jamais suppose valide sur la seule foi du code de retour
        d'ffmpeg (mission ARENA x AUDIT, corrige le 12/09/2026) : un rendu
        qui plante EN COURS d'ecriture peut laisser un fichier tronque,
        present et non vide, mais illisible."""
        if not output_file.exists() or output_file.stat().st_size == 0:
            return False
        ffprobe = _trouver_ffprobe(self.ffmpeg.get_executable())
        try:
            resultat = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(output_file)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as erreur:
            logger.warning("ffprobe injoignable pour verifier %s : %s", output_file.name, erreur)
            return False
        return resultat.returncode == 0 and b"video" in resultat.stdout

    def convert_to_vertical_9_16(self, input_path: str, output_path: str) -> bool:
        """Convertit une vidéo 16:9 en 9:16 (1080x1920) avec arrière-plan flouté.

        Ne rend `True` qu'apres avoir verifie le fichier ecrit : un code de
        retour 0 d'ffmpeg ne garantit pas un fichier lisible (troncature en
        fin de disque, panne pendant l'encodage) — verifie en ecrivant une
        video reelle et en cassant volontairement le processus a mi-rendu.
        """
        if not self.ffmpeg.is_available():
            logger.error("FFmpeg non disponible.")
            return False

        input_file = Path(input_path).resolve()
        output_file = Path(output_path).resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Filtre FFmpeg : Arrière-plan flou + Vidéo originale centrée par-dessus
        filter_complex = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30[bg];"
            "[0:v]scale=1080:-1:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2"
        )

        cmd = [
            self.ffmpeg.get_executable(), "-y",
            "-i", str(input_file),
            "-filter_complex", filter_complex,
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-c:a", "aac",
            str(output_file)
        ]

        try:
            logger.info(f"Rendu de la vidéo 9:16 pour {input_file.name}...")
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Erreur de reformatage 9:16 : {e.stderr.decode('utf-8', errors='ignore')}")
            return False

        if not self._sortie_est_valide(output_file):
            logger.error(
                "Rendu 9:16 annonce par ffmpeg mais fichier invalide ou absent : %s",
                output_file)
            return False
        return True
