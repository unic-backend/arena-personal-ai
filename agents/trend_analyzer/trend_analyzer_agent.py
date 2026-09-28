import logging
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.agent.verification_synthese import avertissement_sources, elements_sans_source
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.security.trust import TrustLevel, wrap
from tools.search.web_search_tool import WebSearchTool

logger = logging.getLogger("usman.agent.trend_analyzer")

class TrendAnalyzerAgent(BaseAgent):
    """Agent d'analyse de tendances (Sénégal, Afrique Francophone, International)."""

    #: Comment l'agent se presente au registre (DEC-0145) : lu par la
    #: decouverte, jamais recopie dans une liste centrale.
    identifiant = "tendances"
    competences = ('tendances', 'idees de contenu', 'videos virales', 'sujets chauds')

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
            f"[{i + 1}] {r['title']} ({r.get('href') or 'sans adresse'}):\n"
            f"{wrap(r['body'], TrustLevel.EXTERNAL, r.get('href') or 'page sans adresse').text}"
            for i, r in enumerate(web_results)
        )

        prompt = f"""Tu es l'agent TrendAnalyzer d'Usman spécialisé sur les tendances du Sénégal, d'Afrique et de l'International.
Analyse ces résultats web récents et synthétise jusqu'à 3 sujets ou tendances clés pour la création de contenu vidéo court.

Règles strictes : chaque tendance s'appuie sur un résultat ci-dessous et le cite par son numéro ([1], [2]...).
N'ajoute aucun chiffre, nom, compte ou événement que ces résultats ne contiennent pas.
S'ils ne suffisent pas pour trois tendances, donne-en moins et dis-le.

Résultats web:
{snippets}

Synthèse des tendances:"""

        # Une synthese « a partir de ces resultats » ne consulte aucun
        # collegue : il repondrait de sa memoire, pas du web (DEC-0150).
        ai_synthesis = (await self.rediger(prompt=prompt, consulter=False)).strip()

        # Relue contre ce qu'elle a recu, jamais reecrite (DEC-0159).
        sans_source = elements_sans_source(ai_synthesis, [prompt, user_input])
        if sans_source:
            logger.warning("Synthese de tendances : elements sans source %s", sans_source)
            ai_synthesis = f"{ai_synthesis}\n\n{avertissement_sources(sans_source)}"

        return {
            "status": "success",
            "agent": self.name,
            "region": region,
            "web_sources_count": len(web_results),
            "sources": [{"title": r.get("title", ""), "url": r.get("href", "")}
                        for r in web_results if r.get("href")],
            "response": ai_synthesis,
            "sans_source": sans_source,
        }
