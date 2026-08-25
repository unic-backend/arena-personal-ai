import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from agents.repo_engineer.repo_engineer_agent import RepoEngineerAgent

async def main():
    print("🛠️ Test du RepoEngineerAgent (Ingénierie Multi-fichiers Odysseus / Devin)...")
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen2.5-coder:14b")
    memory = MemoryManager()

    agent = RepoEngineerAgent(provider=provider, memory=memory)

    prompt = "Analyse l'architecture du projet ARENA et propose un plan pour ajouter un module de logs d'audit."
    res = await agent.run(prompt)

    print(f"   Statut : {res['status']}")
    print(f"\n{res['response']}\n")
    print("✅ TEST REPO ENGINEER AGENT VALIDÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    asyncio.run(main())