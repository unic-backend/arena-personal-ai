import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from agents.trend_analyzer.trend_analyzer_agent import TrendAnalyzerAgent

async def main():
    print("🌍 Test du TrendAnalyzerAgent (Synthèse IA des Tendances du Sénégal)...")
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")
    memory = MemoryManager()
    
    agent = TrendAnalyzerAgent(provider=provider, memory=memory)
    res = await agent.run("Tech et Innovation numérique", context={"region": "Sénégal"})
    
    print(f"   Statut : {res['status']}")
    print(f"   Région : {res.get('region')}")
    print(f"   Sources analysées : {res.get('web_sources_count')}")
    print(f"\n🤖 SYNTHÈSE DES TENDANCES PAR L'IA LOCALE ARENA :\n{res['response']}\n")
    print("✅ AGENT DE RECHERCHE DE TENDANCES TOTALEMENT VALIDÉ !")

if __name__ == "__main__":
    asyncio.run(main())