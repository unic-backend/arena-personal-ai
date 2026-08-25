import sys
from pathlib import Path

# 1. core/agent/base_agent.py
base_agent_code = """from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager

class BaseAgent(ABC):
    \"\"\"Classe abstraite dont héritent tous les agents spécialisés d'ARENA.\"\"\"
    
    def __init__(
        self,
        name: str,
        description: str,
        provider: ModelProvider,
        memory: Optional[MemoryManager] = None
    ):
        self.name = name
        self.description = description
        self.provider = provider
        self.memory = memory

    @abstractmethod
    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        \"\"\"Exécute la tâche principale de l'agent.\"\"\"
        pass
"""
Path("core/agent/base_agent.py").write_text(base_agent_code, encoding="utf-8")
Path("core/agent/__init__.py").write_text("from core.agent.base_agent import BaseAgent\n__all__ = ['BaseAgent']", encoding="utf-8")

# 2. agents/orchestrator/orchestrator_agent.py
orchestrator_code = """import json
import logging
from typing import Dict, Any, Optional
from core.agent.base_agent import BaseAgent
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager

logger = logging.getLogger("arena.agent.orchestrator")

class OrchestratorAgent(BaseAgent):
    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="OrchestratorAgent",
            description="Agent principal chargé d'analyser l'intention utilisateur et d'orienter vers les bons sous-agents.",
            provider=provider,
            memory=memory
        )

    async def analyze_intent(self, user_input: str) -> str:
        \"\"\"Classifie l'intention : CHAT, VIDEO_ANALYSIS, TREND_SEARCH, SYSTEM_STATUS\"\"\"
        prompt = f\"\"\"Analyse l'intention de ce message et réponds UNIQUEMENT par un des mots suivants:
- CHAT (discussion générale, question, salut)
- VIDEO_ANALYSIS (demande d'analyse, découpe ou sous-titrage de vidéo)
- TREND_SEARCH (demande de recherche de tendances ou contenus)
- SYSTEM_STATUS (question sur le système, GPU, mémoire)

Message utilisateur: \"{user_input}\"
Intention:\"\"\"
        try:
            res = await self.provider.generate(prompt=prompt)
            intent = res.strip().upper()
            if "VIDEO" in intent:
                return "VIDEO_ANALYSIS"
            elif "TREND" in intent or "TENDANCE" in intent:
                return "TREND_SEARCH"
            elif "SYSTEM" in intent or "STATUT" in intent:
                return "SYSTEM_STATUS"
            else:
                return "CHAT"
        except Exception as e:
            logger.error(f"Erreur d'analyse d'intention: {e}")
            return "CHAT"

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session_id = context.get("session_id", "default") if context else "default"
        owner_name = self.memory.get_fact("owner") if self.memory else "Saer"
        
        # 1. Classifier l'intention
        intent = await self.analyze_intent(user_input)
        logger.info(f"Intention détectée: {intent}")
        
        # 2. Exécution selon l'intention
        if intent == "CHAT":
            history = self.memory.get_recent_history(session_id=session_id, limit=6) if self.memory else []
            system_prompt = f"Tu es ARENA, l'IA autonome personnelle de {owner_name}. Réponds directement et clairement en français."
            
            prompt_lines = []
            for msg in history:
                role_label = owner_name if msg["role"] == "user" else "ARENA"
                prompt_lines.append(f"{role_label}: {msg['content']}")
            prompt_lines.append(f"{owner_name}: {user_input}")
            prompt_lines.append("ARENA:")
            
            reply = await self.provider.generate(prompt="\\n".join(prompt_lines), system_prompt=system_prompt)
            return {
                "intent": intent,
                "agent": self.name,
                "response": reply.strip()
            }
        else:
            # Mode préparé pour les futurs sous-agents spécialisés
            return {
                "intent": intent,
                "agent": self.name,
                "response": f"[Orchestrator] Intention '{intent}' identifiée. Transmise au module spécialisé (en cours de construction)."
            }
"""
Path("agents/orchestrator/orchestrator_agent.py").write_text(orchestrator_code, encoding="utf-8")
Path("agents/orchestrator/__init__.py").write_text("from agents.orchestrator.orchestrator_agent import OrchestratorAgent\n__all__ = ['OrchestratorAgent']", encoding="utf-8")

# 3. tests/agents/test_orchestrator.py
test_agent_code = """import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from agents.orchestrator.orchestrator_agent import OrchestratorAgent

async def main():
    print("🤖 Test de l'OrchestratorAgent...")
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")
    memory = MemoryManager()
    
    orchestrator = OrchestratorAgent(provider=provider, memory=memory)
    
    # Test 1 : Intention CHAT
    res1 = await orchestrator.run("Bonjour ARENA, qui es-tu ?")
    print(f"Test 1 Intention: {res1['intent']} | Agent: {res1['agent']}")
    print(f"Réponse: {res1['response']}\\n")
    
    # Test 2 : Intention VIDEO
    res2 = await orchestrator.run("Découpe moi cette vidéo YouTube en extrait vertical")
    print(f"Test 2 Intention: {res2['intent']} | Agent: {res2['agent']}")
    print(f"Réponse: {res2['response']}\\n")
    
    print("✅ TEST ORCHESTRATOR EFFECTUÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    asyncio.run(main())
"""
New-Item -ItemType Directory -Force -Path "tests/agents" | Out-Null
Path("tests/agents/test_orchestrator.py").write_text(test_agent_code, encoding="utf-8")

print("✅ Architecture Agent & Orchestrator créée avec succès !")