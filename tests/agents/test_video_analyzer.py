import asyncio
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from tools.video.ffmpeg_tool import FFmpegTool
from agents.video_analyzer.video_analyzer_agent import VideoAnalyzerAgent

async def test_agent():
    print("🎬 Test complet du VideoAnalyzerAgent...")
    
    # 1. Génération d'une vidéo synthétique de test (5s) avec FFmpeg
    test_mp4 = Path("media/source/test_video.mp4")
    test_mp4.parent.mkdir(parents=True, exist_ok=True)
    
    ffmpeg_tool = FFmpegTool()
    cmd = [
        ffmpeg_tool.get_executable(), "-y",
        "-f", "lavfi", "-i", "testsrc=duration=5:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
        "-c:v", "libx264", "-c:a", "aac", str(test_mp4)
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    print("   Vidéo de test générée dans media/source/test_video.mp4")

    # 2. Exécution de l'agent
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")
    memory = MemoryManager()
    
    agent = VideoAnalyzerAgent(provider=provider, memory=memory)
    res = await agent.run(user_input="Analyse cette vidéo", context={"video_path": str(test_mp4)})
    
    print(f"   Statut : {res['status']}")
    print(f"   Vidéo analysée : {res.get('video_name')}")
    print(f"   Durée : {res.get('duration')}s")
    print(f"   Analyse IA : {res.get('ai_analysis')}\n")
    print("✅ TEST VIDEO ANALYZER AGENT RÉUSSI !")

if __name__ == "__main__":
    asyncio.run(test_agent())