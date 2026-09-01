import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.video.crop_tool import CropTool
from tools.video.ffmpeg_tool import FFmpegTool

logger = logging.getLogger("usman.agent.clip_selector")

class ClipSelectorAgent(BaseAgent):
    """Agent autonome de détection et découpe des meilleurs moments viraux."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="ClipSelectorAgent",
            description="Agent de sélection et découpe automatique des passages les plus engageants.",
            provider=provider,
            memory=memory
        )
        self.ffmpeg = FFmpegTool()
        self.crop_tool = CropTool()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        video_path = context.get("video_path") if context else None
        segments = context.get("segments", []) if context else []

        if not video_path or not Path(video_path).exists():
            return {"status": "error", "agent": self.name, "response": "❌ Vidéo source introuvable."}

        src_file = Path(video_path).resolve()

        # Sans segments, rien n'a ete ANALYSE : on prend le debut, et on le
        # dit. Le message annoncait « extrait le plus viral detecte » dans ce
        # cas aussi — une detection qui n'avait pas eu lieu (mesure du
        # 01/09/2026, sur une video de 6,7 s ou il annoncait 15 s).
        start_sec = 0.0
        duration_sec = 15.0
        detecte = False

        if segments:
            # Demande à Qwen 3.5 de trouver le meilleur moment
            segments_str = "\n".join([f"[{s['start']}s -> {s['end']}s] {s['text']}" for s in segments])
            prompt = (
                "Analyse les segments suivants d'une vidéo et identifie le MEILLEUR extrait viral (15 à 45 secondes max).\n"
                "Réponds STRICTEMENT au format JSON avec les clés suivantes : {\"start\": float, \"end\": float, \"reason\": \"explication\"}\n\n"
                f"Segments:\n{segments_str}\n\nJSON:"
            )
            try:
                ai_res = await self.provider.generate(prompt=prompt)
                # Extraction du JSON
                json_start = ai_res.find("{")
                json_end = ai_res.rfind("}") + 1
                if json_start != -1 and json_end != -1:
                    data = json.loads(ai_res[json_start:json_end])
                    start_sec = float(data.get("start", 0.0))
                    end_sec = float(data.get("end", start_sec + 15.0))
                    duration_sec = max(5.0, end_sec - start_sec)
                    detecte = True
            except Exception as e:
                logger.warning(f"Impossible de parser le JSON du moment viral, découpe par défaut : {e}")

        # 1. Découpe du passage sélectionné
        clip_temp = Path("media/clips") / f"{src_file.stem}_best_clip.mp4"
        clip_temp.parent.mkdir(parents=True, exist_ok=True)

        cut_success = self.ffmpeg.cut_video(str(src_file), str(clip_temp), start_sec, duration_sec)
        if not cut_success:
            return {"status": "error", "agent": self.name, "response": "❌ Échec de la découpe FFmpeg."}

        # 2. Reformatage du clip en 9:16 vertical
        rendered_clip = Path("media/rendered") / f"{src_file.stem}_viral_short_9_16.mp4"
        crop_success = self.crop_tool.convert_to_vertical_9_16(str(clip_temp), str(rendered_clip))

        if crop_success:
            # Ce qui est annonce depend de ce qui a REELLEMENT eu lieu : sans
            # analyse, ce n'est pas une detection, c'est un debut de video.
            quoi = ("🔥 Extrait le plus viral détecté"
                    if detecte else
                    "✂️ Aucune analyse disponible : j'ai pris le début de la vidéo")
            return {
                "status": "success",
                "agent": self.name,
                "detecte": detecte,
                "start_sec": start_sec,
                "duration_sec": duration_sec,
                "clip_path": str(rendered_clip),
                "response": (f"{quoi} ({start_sec}s -> {start_sec + duration_sec}s) "
                             f"et reformaté en Short 9:16 : {rendered_clip.name}")
            }
        else:
            return {"status": "error", "agent": self.name, "response": "❌ Échec du reformatage 9:16 de l'extrait."}
