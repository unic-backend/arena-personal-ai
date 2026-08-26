import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("usman.tools.video.subtitle")

class SubtitleTool:
    """Générateur de sous-titres dynamiques CapCut/TikTok avec protection des apostrophes françaises."""

    @staticmethod
    def format_ass_time(seconds: float) -> str:
        centisecs = int((seconds % 1) * 100)
        secs = int(seconds) % 60
        mins = int(seconds // 60) % 60
        hours = int(seconds // 3600)
        return f"{hours}:{mins:02d}:{secs:02d}.{centisecs:02d}"

    def clean_french_text(self, text: str) -> str:
        """Nettoie les erreurs de ponctuations et recolle les contractions (c', d', l')."""
        text = re.sub(r"\b([cCdDlLjJmMnNsStT])\s*['’]\s*", r"\1'", text)
        return text.strip()

    def generate_capcut_ass(self, words_or_segments: List[Dict[str, Any]], output_path: str) -> str:
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTok,Arial,65,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,50,50,280,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        # Reconstitution de paires de mots propres sans isoler d'apostrophes
        raw_words = []
        if words_or_segments and "word" in words_or_segments[0]:
            for item in words_or_segments:
                w_text = self.clean_french_text(item.get("word", ""))
                if w_text and w_text not in ["C", "c", "D", "d", "L", "l", "'", "’"]:
                    raw_words.append({
                        "start": item.get("start", 0.0),
                        "end": item.get("end", 0.0),
                        "word": w_text
                    })
        else:
            for seg in words_or_segments:
                cleaned_seg = self.clean_french_text(seg.get("text", ""))
                words = cleaned_seg.split()
                start = seg.get("start", 0.0)
                end = seg.get("end", 0.0)
                dur = max(0.4, (end - start) / max(1, len(words)))
                for i, w in enumerate(words):
                    w_start = start + (i * dur)
                    w_end = min(end, w_start + dur)
                    raw_words.append({"start": w_start, "end": w_end, "word": w})

        # Regroupement par 2 à 3 mots max
        chunks = []
        current_chunk = []
        for w in raw_words:
            current_chunk.append(w)
            # Ne coupe pas si le mot finit par une apostrophe
            if len(current_chunk) >= 2 and not w["word"].endswith("'"):
                chunks.append(current_chunk)
                current_chunk = []
        if current_chunk:
            chunks.append(current_chunk)

        dialogue_lines = []
        for chunk in chunks:
            if not chunk:
                continue
            start_t = self.format_ass_time(chunk[0]["start"])
            end_t = self.format_ass_time(chunk[-1]["end"])

            words_str = [w["word"] for w in chunk]
            if len(words_str) > 1:
                # Mettre le dernier mot en JAUNE BRILLANT {\c&H00FFFF&}
                highlighted_text = " ".join(words_str[:-1]) + r" {\c&H00FFFF&}" + words_str[-1] + r"{\c&H00FFFFFF&}"
            else:
                highlighted_text = r"{\c&H00FFFF&}" + words_str[0] + r"{\c&H00FFFFFF&}"

            dialogue_lines.append(f"Dialogue: 0,{start_t},{end_t},TikTok,,0,0,0,,{highlighted_text}")

        full_ass = ass_header + "\n".join(dialogue_lines)
        out_file.write_text(full_ass, encoding="utf-8")
        logger.info(f"Fichier ASS CapCut généré : {out_file.name}")
        return str(out_file)
