import logging
from typing import Dict, Any, Optional

from core.agent.base_agent import BaseAgent
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager
from core.reasoning.reasoning_engine import ReasoningEngine

logger = logging.getLogger("arena.agent.orchestrator")

class OrchestratorAgent(BaseAgent):
    """Agent principal de décision et de routage ultra-rapide des tâches."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="OrchestratorAgent",
            description="Agent principal de décision et de routage des tâches.",
            provider=provider,
            memory=memory
        )
        self.reasoning_engine = ReasoningEngine(provider=provider)

    async def analyze_intent(self, user_input: str) -> str:
        """Classifie l'intention de façon instantanée (0.001s) sans bloquer le LLM."""
        text = user_input.lower()

        # Raisonnement profond & Maths complexes
        reasoning_keywords = ["équation", "equation", "résous", "resous", "matrice", "intégrale", "dérivée", "démontre", "démontrer", "calcul complexe", "preuve"]
        if any(k in text for k in reasoning_keywords):
            return "DEEP_REASONING"

        # Mots-clés Code
        code_keywords = ["code", "python", "script", "fonction", "programme", "calcule", "factorielle", "fibonacci", "algorithme", "bug", "erreur", "écris un"]
        if any(k in text for k in code_keywords):
            return "CODE_EXECUTION"

        # Mots-clés Recherche Profonde
        research_keywords = ["étude complète", "rapport détaillé", "recherche approfondie", "étude de marché", "analyse complète", "dossier complet"]
        if any(k in text for k in research_keywords):
            return "DEEP_RESEARCH"

        # Mots-clés Tendances
        trend_keywords = ["tendance", "tendances", "actualité", "actualites", "actu", "sujets chauds", "ce qui se passe"]
        if any(k in text for k in trend_keywords):
            return "TREND_SEARCH"

        # Mots-clés Vidéo
        video_keywords = ["vidéo", "video", "découpe", "sous-titre", "short", "9:16"]
        if any(k in text for k in video_keywords):
            return "VIDEO_ANALYSIS"

        return "CHAT"

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session_id = context.get("session_id", "default") if context else "default"
        owner_name = self.memory.get_fact("owner") if self.memory else "Saer"
        
        intent = await self.analyze_intent(user_input)
        
        if intent == "DEEP_REASONING":
            reasoning_res = await self.reasoning_engine.solve_complex_task(user_input)
            return {
                "intent": intent,
                "agent": "ReasoningEngine",
                "response": reasoning_res["final_response"]
            }

        history = self.memory.get_recent_history(session_id=session_id, limit=6) if self.memory else []
        system_prompt = (
            f"Tu es ARENA, l'IA autonome personnelle de {owner_name}.\n"
            f"Ton propriétaire s'appelle {owner_name}. Réponds en français de manière claire, précise et directe."
        )
        
        prompt_lines = []
        for msg in history:
            role_label = owner_name if msg["role"] == "user" else "ARENA"
            prompt_lines.append(f"{role_label}: {msg['content']}")
        prompt_lines.append(f"{owner_name}: {user_input}")
        prompt_lines.append("ARENA:")
        
        reply = await self.provider.generate(prompt="\n".join(prompt_lines), system_prompt=system_prompt)
        return {
            "intent": intent,
            "agent": self.name,
            "response": reply.strip()
        }