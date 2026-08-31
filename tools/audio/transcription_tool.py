import logging
import os
from pathlib import Path
from typing import Any, Dict

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
logger = logging.getLogger("usman.tools.audio.transcription")


class ModeleAbsent(RuntimeError):
    """Le moteur de transcription n'est pas installe sur cette machine."""

class TranscriptionTool:
    """Outil de transcription audio locale avec horodatage mot par mot (Faster-Whisper)."""

    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
        self.model = None

    def _load_model(self):
        """Charge le modele, ou dit ce qui manque.

        `faster_whisper` est une dependance lourde et optionnelle : elle peut
        manquer sur une machine ou le reste d'ARENA tourne tres bien. Une
        absence se rapporte (`ModeleAbsent`), elle ne remonte pas une
        `ImportError` brute au milieu d'une reponse.
        """
        if self.model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as erreur:
                raise ModeleAbsent(
                    "faster-whisper n'est pas installe : pas de transcription. "
                    "`pip install -r requirements.txt` le remet."
                ) from erreur
            try:
                logger.info(f"Chargement du modèle Whisper ({self.model_size}) sur CPU...")
                self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            except Exception as e:
                logger.error(f"Erreur chargement Whisper : {e}")
                raise e

    def transcribe(self, audio_path: str, language: str = "fr") -> Dict[str, Any]:
        """Transcrit un fichier audio et renvoie le texte avec timestamps par mot."""
        audio_file = Path(audio_path).resolve()
        if not audio_file.exists():
            raise FileNotFoundError(f"Fichier audio introuvable : {audio_path}")

        self._load_model()

        # word_timestamps=True pour obtenir le timing mot par mot (Style CapCut)
        segments, info = self.model.transcribe(
            str(audio_file),
            language=language,
            beam_size=5,
            word_timestamps=True
        )

        segment_list = []
        words_list = []
        full_text = []

        try:
            for seg in segments:
                segment_list.append({
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip()
                })
                full_text.append(seg.text.strip())

                if hasattr(seg, "words") and seg.words:
                    for w in seg.words:
                        words_list.append({
                            "start": round(w.start, 2),
                            "end": round(w.end, 2),
                            "word": w.word.strip()
                        })
        except Exception as e:
            logger.warning(f"Erreur parcours segments : {e}")

        return {
            "language": info.language if info else language,
            # Jamais 0.0 : une duree absente n'est pas une video de zero
            # seconde. Regle du projet — un champ absent n'est pas zero.
            "duration": round(info.duration, 2) if info else None,
            "full_text": " ".join(full_text),
            "segments": segment_list,
            "words": words_list
        }
