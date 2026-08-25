import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from core.agent.base_agent import BaseAgent
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager
from tools.coder.repo_engineer_tool import RepoEngineerTool

logger = logging.getLogger("arena.agent.repo_engineer")

class RepoEngineerAgent(BaseAgent):
    """Agent d'analyse d'architecture multi-fichiers (lecture seule).

    Il LIT la structure du depot et propose un plan. Il ne modifie aucun fichier.
    """

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="RepoEngineerAgent",
            description="Agent d'analyse d'architecture de dépôt, en lecture seule.",
            provider=provider,
            memory=memory
        )
        self.repo_tool = RepoEngineerTool()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info(f"RepoEngineerAgent analyse la tâche projet : {user_input}")

        # 1. Inspection de la structure du dépôt
        tree_list = self.repo_tool.get_tree(max_depth=2)
        tree_str = "\n".join(tree_list[:30])

        prompt = (
            "Tu es RepoEngineerAgent, un ingénieur logiciel principal d'élite (style Devin / Odysseus).\n"
            "Analyse le projet et la tâche suivante, puis propose un diagnostic d'architecture précis.\n\n"
            f"Structure partielle du dépôt :\n{tree_str}\n\n"
            f"Demande de modification / Ingénierie : {user_input}\n\n"
            "Diagnostic & Plan d'Ingénierie Multi-fichiers :"
        )

        analysis = await self.provider.generate(prompt=prompt)

        return {
            "status": "success",
            "agent": self.name,
            "architecture_plan": analysis.strip(),
            "response": (
                "**Rapport d'ingenierie logicielle (RepoEngineerAgent)**\n\n"
                f"{analysis.strip()}\n\n"
                "---\n"
                "*Cet agent analyse et propose. Il ne modifie aucun fichier : "
                "c'est toi qui decides d'appliquer les changements ou non.*"
            )
        }
