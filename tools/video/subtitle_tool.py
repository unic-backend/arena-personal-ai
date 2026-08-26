import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("arena.tools.video.subtitle")

class SubtitleTool:
    """Outil de génération de fichiers de sous-titres SRT / ASS."""

    @staticmethod
    def format_timestamp(seconds: float) -> str:
        """Convertit des secondes en format SRT (00:00:00,000)."""
        millis = int((seconds % 1) * 1000)
        secs = int(seconds) % 60
        mins = int(seconds // 60) % 60
        hours = int(seconds // 3600)
        return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    def generate_srt(self, segments: List[Dict[str, Any]], output_path: str) -> str:
        """Génère un fichier de sous-titres .srt à partir des segments Whisper."""
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        srt_lines = []
        for i, seg in enumerate(segments, start=1):
            start_str = self.format_timestamp(seg.get("start", 0.0))
            end_str = self.format_timestamp(seg.get("end", 0.0))
            text = seg.get("text", "").strip()

            srt_lines.append(f"{i}")
            srt_lines.append(f"{start_str} --> {end_str}")
            srt_lines.append(text)
            srt_lines.append("")

        out_file.write_text("\n".join(srt_lines), encoding="utf-8")
        logger.info(f"Fichier SRT généré : {out_file.name}")
        return str(out_file)
