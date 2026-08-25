import logging
import re
from typing import Dict, Any, Optional

from core.agent.base_agent import BaseAgent
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager

logger = logging.getLogger("arena.agent.orchestrator")

class OrchestratorAgent(BaseAgent):
    """Agent principal de décision et de routage universel."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="OrchestratorAgent",
            description="Agent principal de décision et de routage des tâches.",
            provider=provider,
            memory=memory
        )

    async def analyze_intent(self, user_input: str) -> str:
        """Classifie l'intention de façon instantanée (0.001s)."""
        text = user_input.lower()

        # Trend Search UNIQUEMENT si demande explicite de vidéo/tendances
        if "idée de vidéo" in text or "tendance tiktok" in text or "sujet chaud" in text or "stratégie vidéo" in text:
            return "TREND_SEARCH"

        # Raisonnement profond & Maths complexes
        reasoning_keywords = ["équation", "equation", "résous", "resous", "matrice", "intégrale", "dérivée", "démontre", "démontrer", "calcul complexe", "preuve"]
        if any(k in text for k in reasoning_keywords):
            return "DEEP_REASONING"

        # Code & Programmation
        code_keywords = ["code", "python", "script", "fonction", "programme", "calcule", "factorielle", "fibonacci", "algorithme", "bug", "erreur", "écris un"]
        if any(k in text for k in code_keywords):
            return "CODE_EXECUTION"

        # Recherche Profonde
        research_keywords = ["étude complète", "rapport détaillé", "recherche approfondie", "étude de marché", "dossier complet"]
        if any(k in text for k in research_keywords):
            return "DEEP_RESEARCH"

        # Vidéo
        video_keywords = ["découpe cette vidéo", "reformatte en 9:16", "sous-titre cette vidéo"]
        if any(k in text for k in video_keywords):
            return "VIDEO_ANALYSIS"

        return "CHAT"

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session_id = context.get("session_id", "default") if context else "default"
        owner_name = self.memory.get_fact("owner") if self.memory else "Saer"

        intent = await self.analyze_intent(user_input)

        history = self.memory.get_recent_history(session_id=session_id, limit=6) if self.memory else []
        
        # PROMPT MONDIAL SANS BIAIS LOCAL FORCÉ
        system_prompt = (
            f"Tu es ARENA, une intelligence artificielle internationale de haut niveau, au service de {owner_name}.\n"
            f"Contexte temporel : Nous sommes en 2026.\n"
            f"Règles strictes :\n"
            f"1. Réponds STRICTEMENT et DIRECTEMENT à la question posée sans dériver vers d'autres sujets.\n"
            f"2. Ne parle du Sénégal QUE si la question concerne explicitement le Sénégal.\n"
            f"3. Pour les événements futurs (ex: Coupe du Monde 2026), rappelle poliment que l'événement n'a pas encore eu lieu et donne les faits historiques connus si pertinents.\n"
            f"4. Réponds en français fluide, naturel et professionnel."
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