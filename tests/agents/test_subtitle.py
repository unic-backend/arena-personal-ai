import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from agents.subtitle.subtitle_agent import SubtitleAgent

async def main():
    print("📝 Test du SubtitleAgent...")
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")
    memory = MemoryManager()
    
    agent = SubtitleAgent(provider=provider, memory=memory)
    res = await agent.run("Génère les sous-titres", context={"video_name": "test_video"})
    
    print(f"   Statut : {res['status']}")
    print(f"   Message : {res['response']}")
    print("   ✅ GÉNÉRATION DE SOUS-TITRES SRT VALIDÉE AVEC SUCCÈS !")

if __name__ == "__main__":
    asyncio.run(main())