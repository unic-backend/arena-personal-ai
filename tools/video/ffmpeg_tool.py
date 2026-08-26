import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("usman.tools.video.ffmpeg")

class FFmpegTool:
    """Wrapper complet pour le traitement vidéo et audio via FFmpeg."""

    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()

    def _find_ffmpeg(self) -> str:
        path = shutil.which("ffmpeg")
        if path:
            return path

        user_home = Path.home()
        possible_paths = list(user_home.glob("AppData/Local/Microsoft/WinGet/Packages/**/ffmpeg.exe"))
        possible_paths += list(user_home.glob("AppData/Local/Programs/**/ffmpeg.exe"))

        if possible_paths:
            return str(possible_paths[0].resolve())

        return "ffmpeg"

    def is_available(self) -> bool:
        try:
            res = subprocess.run([self.ffmpeg_path, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode == 0
        except Exception:
            return False

    def get_executable(self) -> str:
        return self.ffmpeg_path

    def extract_audio(self, video_path: str, output_audio_path: str) -> bool:
        """Extrait l'audio d'une vidéo en WAV 16kHz mono pour Whisper."""
        if not self.is_available():
            logger.error("FFmpeg non disponible.")
            return False

        cmd = [
            self.ffmpeg_path, "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_audio_path)
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Erreur extraction audio FFmpeg: {e.stderr.decode('utf-8', errors='ignore')}")
            return False

    def cut_video(self, input_path: str, output_path: str, start_sec: float, duration_sec: float) -> bool:
        """Découpe un extrait vidéo."""
        if not self.is_available():
            return False

        cmd = [
            self.ffmpeg_path, "-y",
            "-ss", str(start_sec),
            "-i", str(input_path),
            "-t", str(duration_sec),
            "-c:v", "libx264",
            "-c:a", "aac",
            str(output_path)
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except Exception as e:
            logger.error(f"Erreur découpe vidéo: {e}")
            return False

    def burn_subtitles(self, video_path: str, sub_path: str, output_path: str) -> bool:
        """Incruste les sous-titres .ass ou .srt directement sur la vidéo."""
        if not self.is_available():
            return False

        sub_file = Path(sub_path).resolve()
        if not sub_file.exists():
            logger.warning(f"Fichier sous-titres introuvable: {sub_path}")
            return False

        clean_sub_path = str(sub_file).replace("\\", "/").replace(":", "\\:")

        # Filtre ASS ou SRT
        if sub_file.suffix.lower() == ".ass":
            sub_filter = f"ass='{clean_sub_path}'"
        else:
            sub_filter = f"subtitles='{clean_sub_path}':force_style='Fontname=Arial,Fontsize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=280'"

        cmd = [
            self.ffmpeg_path, "-y",
            "-i", str(video_path),
            "-vf", sub_filter,
            "-c:v", "libx264",
            "-c:a", "copy",
            str(output_path)
        ]
        try:
            logger.info(f"Incrustation des sous-titres CapCut sur {Path(video_path).name}...")
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except Exception as e:
            logger.error(f"Erreur incrustation sous-titres FFmpeg: {e}")
            return False
