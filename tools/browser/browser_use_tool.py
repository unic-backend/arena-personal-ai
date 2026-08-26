import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("usman.tools.browser_use")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.models.ollama_provider import OllamaProvider


class BrowserUseTool:
    """Outil de navigation Web autonome basé sur Browser-Use et Playwright."""

    def __init__(self, provider: Optional[OllamaProvider] = None):
        self.provider = provider or OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen2.5-coder:14b")

    async def run_task(self, task_instruction: str) -> Dict[str, Any]:
        """Ouvre Chromium de façon autonome, exécute la tâche et renvoie le résultat."""
        logger.info(f"🌐 BrowserUseTool entame la tâche : {task_instruction}")

        try:
            from browser_use import Agent
            from langchain_openai import ChatOpenAI
            from pydantic import Field

            # Classe compatible Pydantic V2 avec le champ provider déclaré
            class CustomChatOpenAI(ChatOpenAI):
                provider: str = Field(default="openai")

            llm = CustomChatOpenAI(
                model=self.provider.model_name,
                base_url=f"{self.provider.base_url}/v1",
                api_key="ollama",
                temperature=0.0
            )

            agent = Agent(
                task=task_instruction,
                llm=llm
            )

            history = await agent.run()
            final_result = history.final_result() if hasattr(history, "final_result") else str(history)

            return {
                "status": "success",
                "task": task_instruction,
                "result": str(final_result)
            }

        except Exception as e:
            logger.error(f"Erreur d'exécution BrowserUse : {e}")
            return {
                "status": "error",
                "task": task_instruction,
                "error": str(e),
                "result": f"❌ Échec de la navigation autonome : {str(e)}"
            }

if __name__ == "__main__":
    print("🌐 Outil BrowserUseTool prêt dans tools/browser/browser_use_tool.py !")
