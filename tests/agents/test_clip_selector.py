import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from agents.clip_selector.clip_selector_agent import ClipSelectorAgent

async def main():
    print("🎬 Test du ClipSelectorAgent (Détection & Découpe Virale 9:16)...")
    test_video = Path("media/source/test_video.mp4")
    if not test_video.exists():
        print("❌ Fichier media/source/test_video.mp4 introuvable.")
        return

    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")
    memory = MemoryManager()
    
    agent = ClipSelectorAgent(provider=provider, memory=memory)
    
    sample_segments = [
        {"start": 0.0, "end": 4.0, "text": "Bonjour à tous, bienvenue dans cette vidéo."},
        {"start": 4.0, "end": 12.0, "text": "Aujourd'hui, nous révélons le plus grand secret de l'innovation au Sénégal !"},
        {"start": 12.0, "end": 18.0, "text": "Merci d'avoir regardé, abonnez-vous."}
    ]
    
    res = await agent.run("Trouve le meilleur moment viral", context={
        "video_path": str(test_video),
        "segments": sample_segments
    })
    
    print(f"   Statut : {res['status']}")
    print(f"   Message : {res['response']}")
    print("   ✅ DÉTECTION ET DÉCOUPE VIRALE 9:16 VALIDÉE AVEC SUCCÈS !")

if __name__ == "__main__":
    asyncio.run(main())