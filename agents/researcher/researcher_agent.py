import logging
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.search.web_search_tool import WebSearchTool

logger = logging.getLogger("arena.agent.researcher")

class DeepResearcherAgent(BaseAgent):
    """Agent de recherche profonde multi-sources (Pattern Kimi / Perplexity)."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="DeepResearcherAgent",
            description="Agent de recherche approfondie, croisement de sources et rapports d'intelligence.",
            provider=provider,
            memory=memory
        )
        self.search_tool = WebSearchTool()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info(f"DeepResearcherAgent entame une recherche approfondie sur : {user_input}")

        # 1. Élaboration du plan de recherche
        plan_prompt = (
            "Tu es un directeur de recherche stratégique.\n"
            "Définis 3 mots-clés de recherche Web complémentaires pour explorer ce sujet sous tous ses angles (technique, économique, impact local/Sénégal).\n"
            "Réponds UNIQUEMENT avec 3 lignes contenant chacune un mot-clé de recherche, sans numérotation ni puce.\n\n"
            f"Sujet de recherche: {user_input}"
        )

        plan_res = await self.provider.generate(prompt=plan_prompt)
        queries = [q.strip() for q in plan_res.strip().split("\n") if q.strip()][:3]
        if not queries:
            queries = [user_input]

        # 2. Exécution des recherches croisées
        all_results = []
        for q in queries:
            results = self.search_tool.search(q, max_results=3)
            all_results.extend(results)

        # Elimination des doublons d'URL
        unique_sources = []
        seen_urls = set()
        for r in all_results:
            if r["href"] not in seen_urls:
                seen_urls.add(r["href"])
                unique_sources.append(r)

        # 3. Synthèse d'intelligence de haut niveau
        sources_text = "\n".join([f"[{i+1}] {s['title']} ({s['href']})\n{s['body']}\n" for i, s in enumerate(unique_sources)])

        synthesis_prompt = (
            "Tu es DeepResearcherAgent d'ARENA, un expert en analyse stratégique d'élite.\n"
            "Rédige un Rapport d'Intelligence de Haut Niveau à partir des données web collectées ci-dessous.\n\n"
            "Structure attendue :\n"
            "1. 📌 **Synthèse Exécutive** (Vue d'ensemble)\n"
            "2. 💡 **Analyse Prise de Décision & Opportunités** (Points clés)\n"
            "3. 🇸🇳 **Impact & Stratégie Sénégal / Afrique / International**\n"
            "4. 🔗 **Sources Consultées**\n\n"
            f"Sujet principal : {user_input}\n\n"
            f"Données Web :\n{sources_text}\n\n"
            "Rapport d'Intelligence :"
        )

        synthesis = await self.provider.generate(prompt=synthesis_prompt)

        return {
            "status": "success",
            "agent": self.name,
            "queries_used": queries,
            "sources_count": len(unique_sources),
            "response": synthesis.strip()
        }
