import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("usman.tools.browser_use")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.backend.config import MODELE_RAPIDE, OLLAMA_URL
from core.models.ollama_provider import OllamaProvider


class BrowserUseTool:
    """Outil de navigation Web autonome basé sur Browser-Use et Playwright."""

    def __init__(self, provider: Optional[OllamaProvider] = None):
        # L'adresse et le modele viennent de la configuration, jamais du code :
        # ecrits en dur ici, un Ollama deplace ou un modele change dans `.env`
        # laissait TOUT marcher sauf la navigation, avec une erreur nommant
        # une adresse que le proprietaire n'avait pas configuree.
        self.provider = provider or OllamaProvider(
            base_url=OLLAMA_URL, model_name=MODELE_RAPIDE)

    async def run_task(self, task_instruction: str, cdp_url: Optional[str] = None) -> Dict[str, Any]:
        """Ouvre Chromium de façon autonome, exécute la tâche et renvoie le résultat.

        `cdp_url` : quand fourni, `browser_use` se CONNECTE à un navigateur
        DÉJÀ lancé ailleurs (ex. Lightpanda, `lightpanda serve`) au lieu
        d'en démarrer un nouveau — même paramètre que `browser_use.
        BrowserSession(cdp_url=...)`, vérifié directement dans le code
        installé (`browser_use/browser/session.py`). `None` (le défaut)
        laisse `browser_use` lancer SON PROPRE Chromium local via
        Playwright, exactement le comportement d'avant ce paramètre —
        aucun changement pour un appelant qui ne le fournit pas.
        """
        logger.info(f"🌐 BrowserUseTool entame la tâche : {task_instruction}")

        try:
            from browser_use import Agent
            from browser_use.browser.session import BrowserSession
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

            browser_session = BrowserSession(cdp_url=cdp_url) if cdp_url else None

            agent = Agent(
                task=task_instruction,
                llm=llm,
                browser_session=browser_session,
            )

            history = await agent.run()
            final_result = history.final_result() if hasattr(history, "final_result") else str(history)

            return {
                "status": "success",
                "task": task_instruction,
                "result": str(final_result),
                "moteur": "lightpanda" if cdp_url else "chromium",
            }

        except Exception as e:
            logger.error(f"Erreur d'exécution BrowserUse : {e}")
            return {
                "status": "error",
                "task": task_instruction,
                "error": str(e),
                "result": f"❌ Échec de la navigation autonome : {str(e)}",
                "moteur": "lightpanda" if cdp_url else "chromium",
            }

if __name__ == "__main__":
    print("🌐 Outil BrowserUseTool prêt dans tools/browser/browser_use_tool.py !")
