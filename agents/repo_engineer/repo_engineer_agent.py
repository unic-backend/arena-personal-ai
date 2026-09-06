import logging
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.specialistes.selection import bloc_de_methode, choisir
from tools.coder.repo_engineer_tool import RepoEngineerTool

logger = logging.getLogger("usman.agent.repo_engineer")

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

        # Meme defaut que DEC-0061 (OpenViking) : une methode de specialiste
        # declaree pour REPO_ENGINEERING (`tests`, `architecture`,
        # `core/specialistes/catalogue.py`) n'atteignait jamais cet agent —
        # seul le repli conversationnel la composait, un chemin que
        # REPO_ENGINEERING ne prend jamais puisqu'il est deja aiguille ici.
        methode = bloc_de_methode(choisir(user_input, "REPO_ENGINEERING"))

        prompt = (
            "Tu es RepoEngineerAgent, un ingénieur logiciel principal d'élite (style Devin / Odysseus).\n"
            "Analyse le projet et la tâche suivante, puis propose un diagnostic d'architecture précis.\n\n"
            f"Structure partielle du dépôt :\n{tree_str}\n\n"
            f"Demande de modification / Ingénierie : {user_input}\n\n"
            "Diagnostic & Plan d'Ingénierie Multi-fichiers :"
            + (f"\n\n{methode}" if methode else "")
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
