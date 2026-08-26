import logging
import os
from pathlib import Path
from typing import Any, Dict

# Masquer l'avertissement de liens symboliques sous Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

logger = logging.getLogger("arena.tools.audio.transcription")

class TranscriptionTool:
    """Outil de transcription audio locale robuste (Faster-Whisper)."""

    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
        self.model = None

    def _load_model(self):
        if self.model is None:
            from faster_whisper import WhisperModel

            # Essai CPU sécurisé (rapide, sans dépendance CUDA externe requise)
            try:
                logger.info(f"Chargement du modèle Whisper ({self.model_size}) sur CPU...")
                self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                logger.info("Modèle Whisper prêt sur CPU.")
            except Exception as e:
                logger.error(f"Erreur chargement Whisper : {e}")
                raise e

    def transcribe(self, audio_path: str, language: str = "fr") -> Dict[str, Any]:
        """Transcrit un fichier audio et renvoie le texte avec timestamps."""
        audio_file = Path(audio_path).resolve()
        if not audio_file.exists():
            raise FileNotFoundError(f"Fichier audio introuvable : {audio_path}")

        self._load_model()

        segments, info = self.model.transcribe(
            str(audio_file),
            language=language,
            beam_size=5
        )

        segment_list = []
        full_text = []

        try:
            for seg in segments:
                segment_list.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip()
                })
                full_text.append(seg.text.strip())
        except Exception as e:
            logger.warning(f"Erreur parcours segments : {e}")

        return {
            "language": info.language if info else language,
            "language_probability": round(info.language_probability, 2) if info else 1.0,
            "duration": round(info.duration, 2) if info else 0.0,
            "full_text": " ".join(full_text),
            "segments": segment_list
        }

if __name__ == "__main__":
    print("🎙️ Outil TranscriptionTool mis à jour !")
