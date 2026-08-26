import logging
import subprocess
from pathlib import Path

from tools.video.ffmpeg_tool import FFmpegTool

logger = logging.getLogger("arena.tools.video.crop")

class CropTool:
    """Outil de recadrage et de conversion vers le format vertical 9:16 (1080x1920)."""

    def __init__(self):
        self.ffmpeg = FFmpegTool()

    def convert_to_vertical_9_16(self, input_path: str, output_path: str) -> bool:
        """Convertit une vidéo 16:9 en 9:16 (1080x1920) avec arrière-plan flouté."""
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
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Erreur de reformatage 9:16 : {e.stderr.decode('utf-8', errors='ignore')}")
            return False
