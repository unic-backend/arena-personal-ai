"""Agent Executive Intelligence — mission ARENA x OPENEXECUTIVE (DEC-0086).

Meme convention que `agents/finance/finance_agent.py` : un `BaseAgent` mince
qui compose des capacites deja reelles (`core/executive/moteur.py`), jamais
un second agent-plateforme. Aucune capacite d'ecriture n'est appelee ici —
cet agent RECOMMANDE (mission §23/§24) ; toute action consequente reste
soumise au systeme de permission d'ARENA, inchange.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from core.agent.base_agent import BaseAgent
from core.executive.moteur import MoteurExecutif
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.search.web_search_tool import WebSearchTool

logger = logging.getLogger("usman.agent.executive")


def _chercheur_web(outil: WebSearchTool) -> Callable[[str], List[Dict[str, str]]]:
    """Adapte `WebSearchTool.search` a la signature attendue par les roles
    (mission §20) — le meme outil que FinanceAgent/DeepResearcherAgent,
    jamais un second moteur de recherche."""

    def _chercher(question: str) -> List[Dict[str, str]]:
        try:
            return outil.search(question, max_results=3, recent=True) or []
        except Exception as erreur:  # noqa: BLE001 — une recherche en panne ne bloque jamais l'analyse
            logger.warning("Recherche executive en echec : %s", erreur)
            return []

    return _chercher


class ExecutiveAgent(BaseAgent):
    """Coordonne les specialistes existants d'ARENA pour une decision
    d'affaires — jamais un CEO artificiel qui joue un role (mission §5)."""

    def __init__(
        self,
        provider: ModelProvider,
        memory: Optional[MemoryManager] = None,
        recherche: Optional[Any] = None,
        lightrag_query: Optional[Callable[[str], str]] = None,
    ):
        super().__init__(
            name="ExecutiveAgent",
            description="Executive Intelligence : coordonne les specialistes existants "
                        "d'ARENA pour une decision d'affaires.",
            provider=provider,
            memory=memory,
        )
        outil_recherche = recherche if recherche is not None else WebSearchTool()
        self.moteur = MoteurExecutif(
            provider=provider, memory=memory,
            lightrag_query=lightrag_query,
            chercheur=_chercheur_web(outil_recherche),
        )

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        decision = await self.moteur.analyser(user_input)
        return {
            "status": "success",
            "agent": self.name,
            "response": decision.reponse,
            "executive_decision": decision.to_dict(),
        }
