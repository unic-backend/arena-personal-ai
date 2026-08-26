import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.video.crop_tool import CropTool
from tools.video.ffmpeg_tool import FFmpegTool

logger = logging.getLogger("usman.agent.editor")

class EditorAgent(BaseAgent):
    """Agent monteur vidéo chargé du recadrage vertical et du découpage."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="EditorAgent",
            description="Agent de montage et reformatage vidéo 9:16.",
            provider=provider,
            memory=memory
        )
        self.crop_tool = CropTool()
        self.ffmpeg = FFmpegTool()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        video_path = context.get("video_path") if context else None
        if not video_path or not Path(video_path).exists():
            return {"status": "error", "agent": self.name, "response": "❌ Vidéo introuvable."}

        src_file = Path(video_path)
        rendered_file = Path("media/rendered") / f"{src_file.stem}_vertical_9_16.mp4"

        success = self.crop_tool.convert_to_vertical_9_16(str(src_file), str(rendered_file))
        if success:
            return {
                "status": "success",
                "agent": self.name,
                "rendered_path": str(rendered_file),
                "response": f"✅ Vidéo reformatée au format vertical 9:16 (1080x1920) avec succès : {rendered_file.name}"
            }
        else:
            return {"status": "error", "agent": self.name, "response": "❌ Échec du rendu 9:16."}
