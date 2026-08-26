import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.video.subtitle_tool import SubtitleTool

logger = logging.getLogger("usman.agent.subtitle")

class SubtitleAgent(BaseAgent):
    """Agent chargé de la correction contextuelle et de la génération des sous-titres CapCut/TikTok."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="SubtitleAgent",
            description="Agent de correction orthographique contextuelle et formatage de sous-titres CapCut/TikTok.",
            provider=provider,
            memory=memory
        )
        self.sub_tool = SubtitleTool()

    async def correct_words_contextually(self, words_or_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Utilise l'IA pour corriger les fautes d'homophones phonétiques (ex: 'de vie' -> 'devis')."""
        if not words_or_segments:
            return []

        # Extraire le texte brut
        if "word" in words_or_segments[0]:
            full_text = " ".join([w.get("word", "") for w in words_or_segments])
        else:
            full_text = " ".join([s.get("text", "") for s in words_or_segments])

        prompt = (
            "Tu es un correcteur orthographique expert spécialisé dans la correction de transcriptions audio.\n"
            "Ta mission: Corriger les erreurs d'écoute phonétiques évidentes selon le sujet métier de la vidéo.\n"
            "Exemples fréquents: 'de vie' -> 'devis', 'en compétant' -> 'en compétent', 'plaqué' -> 'plaque'.\n"
            "Règles strictes:\n"
            "1. Ne rajoute AUCUNE explication ou commentaire.\n"
            "2. Garde la même structure de phrase.\n"
            "3. Réponds UNIQUEMENT avec le texte corrigé.\n\n"
            f"Texte brut: {full_text}\n"
            "Texte corrigé:"
        )

        try:
            logger.info("Correction orthographique contextuelle via l'IA...")
            corrected_text = await self.provider.generate(prompt=prompt)
            corrected_words = corrected_text.strip().split()

            # Application des mots corrigés sur les objets de timing
            if "word" in words_or_segments[0] and len(corrected_words) == len(words_or_segments):
                for i, w_obj in enumerate(words_or_segments):
                    w_obj["word"] = corrected_words[i]
            elif "text" in words_or_segments[0]:
                for seg in words_or_segments:
                    seg["text"] = self.sub_tool.clean_french_text(seg.get("text", ""))
        except Exception as e:
            logger.warning(f"Impossible d'effectuer la correction contextuelle : {e}")

        return words_or_segments

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        words = context.get("words") if context else None
        segments = context.get("segments") if context else None
        video_name = context.get("video_name", "output") if context else "output"

        data_to_use = words if words else segments
        if not data_to_use:
            data_to_use = [
                {"start": 0.0, "end": 2.5, "text": "Bienvenue sur Usman"},
                {"start": 2.5, "end": 5.0, "text": "Sous titres TikTok automatiques"}
            ]

        # 1. Correction orthographique par l'IA (Qwen 3.5)
        data_to_use = await self.correct_words_contextually(data_to_use)

        # 2. Génération des sous-titres .ass CapCut
        output_ass = Path("media/subtitles") / f"{video_name}.ass"
        ass_path = self.sub_tool.generate_capcut_ass(data_to_use, str(output_ass))

        return {
            "status": "success",
            "agent": self.name,
            "ass_path": ass_path,
            "srt_path": ass_path,
            "response": f"✅ Sous-titres CapCut corrigés et générés : {Path(ass_path).name}"
        }
