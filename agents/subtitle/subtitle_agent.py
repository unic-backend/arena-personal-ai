import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.video.subtitle_tool import SubtitleTool

logger = logging.getLogger("arena.agent.subtitle")

class SubtitleAgent(BaseAgent):
    """Agent chargé de la création des sous-titres pour le contenu vidéo."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="SubtitleAgent",
            description="Agent de génération et formatage de sous-titres.",
            provider=provider,
            memory=memory
        )
        self.sub_tool = SubtitleTool()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        segments = context.get("segments") if context else None
        video_name = context.get("video_name", "output") if context else "output"

        if not segments:
            # Segments par défaut si aucun extrait audio réel fourni
            segments = [
                {"start": 0.0, "end": 2.5, "text": "Bienvenue sur l'IA Personnelle ARENA !"},
                {"start": 2.5, "end": 5.0, "text": "Découpe et sous-titrage automatique 9:16."}
            ]

        output_srt = Path("media/subtitles") / f"{video_name}.srt"
        srt_path = self.sub_tool.generate_srt(segments, str(output_srt))

        return {
            "status": "success",
            "agent": self.name,
            "srt_path": srt_path,
            "response": f"✅ Sous-titres SRT générés avec succès : {Path(srt_path).name}"
        }
