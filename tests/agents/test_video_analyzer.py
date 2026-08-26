"""VideoAnalyzerAgent : analyse d'une vidéo réelle. Exige ffmpeg, Whisper et Ollama."""
import pytest

from agents.video_analyzer.video_analyzer_agent import VideoAnalyzerAgent


@pytest.mark.integration
async def test_l_agent_analyse_une_video_synthetique(ollama_en_ligne, video_de_test, memoire):
    agent = VideoAnalyzerAgent(provider=ollama_en_ligne, memory=memoire)

    res = await agent.run("Analyse cette vidéo", context={"video_path": str(video_de_test)})

    assert res["status"] == "success"
    assert res["video_name"] == video_de_test.stem
    assert res["duration"] == pytest.approx(5.0, abs=0.5)
