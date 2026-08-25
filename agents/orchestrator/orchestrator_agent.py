import json
import logging
from typing import Dict, Any, Optional

from core.agent.base_agent import BaseAgent
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager

logger = logging.getLogger("arena.agent.orchestrator")

class OrchestratorAgent(BaseAgent):
    """Agent principal chargé d'analyser l'intention utilisateur et d'orienter vers les sous-agents."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="OrchestratorAgent",
            description="Agent principal de décision et de routage des tâches.",
            provider=provider,
            memory=memory
        )

    async def analyze_intent(self, user_input: str) -> str:
        """Classifie l'intention : CHAT, CODE_EXECUTION, DEEP_RESEARCH, VIDEO_ANALYSIS, TREND_SEARCH"""
        prompt = (
            "Analyse l'intention de ce message et réponds UNIQUEMENT par un des mots suivants:\n"
            "- DEEP_RESEARCH (demande de recherche approfondie, étude complète, analyse détaillée, rapport complet, étude de marché)\n"
            "- CODE_EXECUTION (demande d'écrire du code, script, algorithme, fonction Python, calcul complexe)\n"
            "- VIDEO_ANALYSIS (demande d'analyser, découper ou sous-titrer une vidéo)\n"
            "- TREND_SEARCH (demande de rechercher des tendances rapides, actualités ou sujets chauds)\n"
            "- CHAT (discussion générale, question simple, bonjour, politesse)\n\n"
            f"Message utilisateur: \"{user_input}\"\n"
            "Intention:"
        )
        try:
            res = await self.provider.generate(prompt=prompt)
            intent = res.strip().upper()
            if "RESEARCH" in intent or "ETUDE" in intent or "RAPPORT" in intent:
                return "DEEP_RESEARCH"
            elif "CODE" in intent or "SCRIPT" in intent or "PROGRAMME" in intent:
                return "CODE_EXECUTION"
            elif "VIDEO" in intent:
                return "VIDEO_ANALYSIS"
            elif "TREND" in intent or "TENDANCE" in intent:
                return "TREND_SEARCH"
            else:
                return "CHAT"
        except Exception as e:
            logger.error(f"Erreur classification d'intention: {e}")
            return "CHAT"

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session_id = context.get("session_id", "default") if context else "default"
        owner_name = self.memory.get_fact("owner") if self.memory else "Saer"
        
        intent = await self.analyze_intent(user_input)
        logger.info(f"Intention détectée par l'Orchestrateur : {intent}")

        if intent == "CHAT":
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
        else:
            return {
                "intent": intent,
                "agent": self.name,
                "response": f"[Orchestrator] Intention '{intent}' identifiée. Routage vers le module spécialisé."
            }