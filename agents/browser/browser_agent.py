import logging
from typing import Dict, Any, Optional

from core.agent.base_agent import BaseAgent
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager
from tools.browser.browser_use_tool import BrowserUseTool

logger = logging.getLogger("arena.agent.browser")

class BrowserAgent(BaseAgent):
    """Agent autonome de navigation Web active (Playwright + Browser-Use)."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="BrowserAgent",
            description="Agent autonome de pilotage du navigateur Web (clics, formulaires, scraping dynamique).",
            provider=provider,
            memory=memory
        )
        self.browser_tool = BrowserUseTool()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info(f"BrowserAgent au travail sur la tâche : {user_input}")
        
        result = await self.browser_tool.run_task(user_input)

        if result["status"] == "success":
            return {
                "status": "success",
                "agent": self.name,
                "response": f"🌐 **Navigation Web Autonome Accomplie !**\n\n**Tâche :** {user_input}\n\n**Résultat :**\n{result['result']}"
            }
        else:
            return {
                "status": "error",
                "agent": self.name,
                "response": f"❌ Échec de la navigation Web autonome : {result.get('error', 'Erreur inconnue')}"
            }