import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from core.agent.base_agent import BaseAgent
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager
from tools.coder.swe_aci_tool import SWEACITool

logger = logging.getLogger("arena.agent.swe")

class SWEAgent(BaseAgent):
    """Agent d'ingénierie chirurgicale et de résolution de bugs (Princeton NLP SWE-agent Pattern)."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="SWEAgent",
            description="Agent de résolution chirurgicale de bugs basé sur le protocole ACI (Princeton NLP).",
            provider=provider,
            memory=memory
        )
        self.aci = SWEACITool()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info(f"SWEAgent entame la résolution chirurgicale du problème : {user_input}")

        # 1. Recherche ACI des fichiers impactés
        search_res = self.aci.search_dir(user_input.split()[0] if user_input else "def")

        prompt = (
            "Tu es SWEAgent, un ingénieur de recherche d'élite utilisant le protocole ACI (Princeton NLP).\n"
            "Analyse ce problème de code et les occurrences trouvées dans le dépôt, puis propose la correction chirurgicale exacte.\n\n"
            f"Occurrences ACI trouvées :\n{search_res}\n\n"
            f"Problème à résoudre : {user_input}\n\n"
            "Analyse Chirurgicale & Plan de Correction :"
        )

        analysis = await self.provider.generate(prompt=prompt)

        return {
            "status": "success",
            "agent": self.name,
            "search_matches": search_res,
            "response": f"🖥️ **Rapport de Résolution Chirurgicale ACI (Princeton NLP SWE-agent)**\n\n{analysis.strip()}"
        }