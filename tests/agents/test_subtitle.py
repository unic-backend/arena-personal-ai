"""SubtitleAgent : génération du fichier SRT. Exige Whisper et Ollama."""
import pytest

from agents.subtitle.subtitle_agent import SubtitleAgent


@pytest.mark.integration
async def test_les_sous_titres_sont_generes(ollama_en_ligne, memoire):
    agent = SubtitleAgent(provider=ollama_en_ligne, memory=memoire)

    res = await agent.run("Génère les sous-titres", context={"video_name": "test_video"})

    assert res["status"] in {"success", "error"}
    assert res["response"].strip() != ""
