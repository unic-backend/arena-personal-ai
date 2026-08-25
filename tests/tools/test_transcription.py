import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.video.ffmpeg_tool import FFmpegTool
from tools.audio.transcription_tool import TranscriptionTool

def test_whisper():
    print("🎙️ Test de transcription locale Whisper...")
    
    ffmpeg_tool = FFmpegTool()
    if not ffmpeg_tool.is_available():
        print("❌ FFmpeg introuvable pour générer l'échantillon de test.")
        return

    test_wav = Path("media/analysis/test_sample.wav")
    test_wav.parent.mkdir(parents=True, exist_ok=True)
    
    # Utilisation du chemin exact de FFmpeg
    cmd = [
        ffmpeg_tool.get_executable(), "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
        "-ar", "16000", "-ac", "1", str(test_wav)
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    print("   Échantillon audio synthétique créé.")
    
    tool = TranscriptionTool(model_size="tiny")
    res = tool.transcribe(str(test_wav))
    
    print(f"   Durée audio détectée : {res['duration']}s")
    print(f"   Langue détectée : {res['language']}")
    print("   ✅ MODULE WHISPER LOCAL VALIDÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    test_whisper()