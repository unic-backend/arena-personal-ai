import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.audio.transcription_tool import TranscriptionTool
from tools.video.ffmpeg_tool import FFmpegTool

logger = logging.getLogger("arena.agent.video_analyzer")

class VideoAnalyzerAgent(BaseAgent):
    """Agent chargé de transcrire et d'analyser le contenu d'une vidéo."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="VideoAnalyzerAgent",
            description="Agent d'analyse de contenu vidéo et de détection de passages clés.",
            provider=provider,
            memory=memory
        )
        self.ffmpeg = FFmpegTool()
        self.transcriber = TranscriptionTool(model_size="tiny")

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        video_path = context.get("video_path") if context else None

        if not video_path or not Path(video_path).exists():
            return {
                "status": "error",
                "agent": self.name,
                "response": "❌ Aucune vidéo valide fournie pour l'analyse."
            }

        video_file = Path(video_path)
        audio_output = video_file.parent / f"{video_file.stem}_extracted.wav"

        # 1. Extraction Audio avec FFmpeg
        logger.info(f"Extraction audio de {video_file.name}...")
        extracted = self.ffmpeg.extract_audio(str(video_file), str(audio_output))
        if not extracted:
            return {
                "status": "error",
                "agent": self.name,
                "response": "❌ Échec de l'extraction audio via FFmpeg."
            }

        # 2. Transcription locale avec Whisper
        logger.info("Transcription audio via Whisper...")
        transcription_res = self.transcriber.transcribe(str(audio_output))
        full_text = transcription_res.get("full_text", "")

        # 3. Analyse du contenu par Qwen 3.5
        prompt = f"""Tu es un expert en analyse vidéo. Analyse la transcription suivante et propose :
1. Un résumé concis du contenu.
2. Les thèmes principaux abordés.
3. Une note de potentiel pour en faire un extrait court (Short/TikTok) de 0 à 10.

Transcription: "{full_text}"
Analyse:"""

        ai_analysis = await self.provider.generate(prompt=prompt)

        return {
            "status": "success",
            "agent": self.name,
            "video_name": video_file.name,
            "duration": transcription_res.get("duration"),
            "transcription": full_text,
            "segments": transcription_res.get("segments"),
            "ai_analysis": ai_analysis.strip()
        }
