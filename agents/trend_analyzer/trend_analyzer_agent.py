import logging
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.security.trust import TrustLevel, wrap
from tools.search.web_search_tool import WebSearchTool

logger = logging.getLogger("usman.agent.trend_analyzer")

class TrendAnalyzerAgent(BaseAgent):
    """Agent d'analyse de tendances (Sénégal, Afrique Francophone, International)."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="TrendAnalyzerAgent",
            description="Agent de découverte et synthèse des tendances actuelles.",
            provider=provider,
            memory=memory
        )
        self.search_tool = WebSearchTool()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        region = context.get("region", "Sénégal & Afrique") if context else "Sénégal & Afrique"
        query = f"Tendances actualités {region} {user_input}"

        logger.info(f"Recherche de tendances pour: {query}...")
        web_results = self.search_tool.search(query, max_results=4)

        if not web_results:
            return {
                "status": "warning",
                "agent": self.name,
                "response": "⚠️ Aucune donnée récente trouvée sur le web pour cette recherche."
            }

        # Formatage des résultats web pour l'IA
        # Meme regle que `FreshInfoAgent` : une page que personne ne controle
        # entre enveloppee, jamais telle quelle.
        snippets = "\n".join(
            f"- {r['title']}:\n"
            f"{wrap(r['body'], TrustLevel.EXTERNAL, r.get('href') or 'page sans adresse').text}"
            for r in web_results
        )

        prompt = f"""Tu es l'agent TrendAnalyzer d'Usman spécialisé sur les tendances du Sénégal, d'Afrique et de l'International.
Analyse ces résultats web récents et synthétise 3 sujets ou tendances clés pour la création de contenu vidéo court:

Résultats web:
{snippets}

Synthèse des tendances:"""

        ai_synthesis = await self.provider.generate(prompt=prompt)

        return {
            "status": "success",
            "agent": self.name,
            "region": region,
            "web_sources_count": len(web_results),
            "response": ai_synthesis.strip()
        }
