import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from agents.publisher.publisher_agent import PublisherAgent

async def main():
    print("🚀 Test du PublisherAgent (Sécurité & Simulation)...")
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")
    
    agent = PublisherAgent(provider=provider)
    
    # On simule la publication de notre vidéo de test existante
    test_vid = Path("media/source/test_video.mp4")
    res = await agent.run(user_input="Les tendances tech au Sénégal", context={"video_path": str(test_vid)})
    
    print(f"\nStatut: {res['status']}")
    print(f"Message de l'Agent :\n{res['response']}\n")
    print("✅ TEST PUBLISHER AGENT (SIMULATION) RÉUSSI !")

if __name__ == "__main__":
    asyncio.run(main())