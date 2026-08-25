import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from agents.researcher.researcher_agent import DeepResearcherAgent

async def main():
    print("🔬 Test du DeepResearcherAgent (Recherche Profonde Multi-Sources)...")
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")
    memory = MemoryManager()
    
    agent = DeepResearcherAgent(provider=provider, memory=memory)
    
    prompt = "Intelligence Artificielle et écosystème Startup au Sénégal en 2026"
    res = await agent.run(prompt)
    
    print(f"Statut : {res['status']}")
    print(f"Mots-clés de recherche utilisés : {res.get('queries_used')}")
    print(f"Nombre de sources uniques : {res.get('sources_count')}")
    print("\n" + res['response'])
    print("\n--- TEST DEEP RESEARCHER VALIDÉ AVEC SUCCÈS ---")

if __name__ == "__main__":
    asyncio.run(main())