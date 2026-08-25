import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from agents.swe_agent.swe_agent import SWEAgent

async def main():
    print("🖥️ Test du SWEAgent (Princeton NLP ACI Pattern)...")
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen2.5-coder:14b")
    memory = MemoryManager()

    agent = SWEAgent(provider=provider, memory=memory)

    prompt = "Corrige l'erreur d'encodage UTF-8 dans la lecture des fichiers de configuration."
    res = await agent.run(prompt)

    print(f"   Statut : {res['status']}")
    print(f"\n{res['response']}\n")
    print("✅ TEST SWE-AGENT PRINCETON NLP VALIDÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    asyncio.run(main())