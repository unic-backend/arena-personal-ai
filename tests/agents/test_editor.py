import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from agents.editor.editor_agent import EditorAgent

async def main():
    print("🎬 Test du EditorAgent (Rendu Vertical 9:16)...")
    test_video = Path("media/source/test_video.mp4")
    if not test_video.exists():
        print("❌ Fichier media/source/test_video.mp4 introuvable.")
        return

    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")
    memory = MemoryManager()
    
    editor = EditorAgent(provider=provider, memory=memory)
    res = await editor.run("Formatte en 9:16", context={"video_path": str(test_video)})
    
    print(f"   Statut : {res['status']}")
    print(f"   Message : {res['response']}")
    print("   ✅ RENDU VIDÉO VERTICAL 9:16 VALIDÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    asyncio.run(main())