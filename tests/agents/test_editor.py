"""EditorAgent : recadrage vertical 9:16. Exige ffmpeg et Ollama."""
import pytest

from agents.editor.editor_agent import EditorAgent


@pytest.mark.integration
async def test_le_rendu_vertical_est_produit(ollama_en_ligne, video_de_test, memoire):
    agent = EditorAgent(provider=ollama_en_ligne, memory=memoire)

    res = await agent.run("Formatte en 9:16", context={"video_path": str(video_de_test)})

    assert res["status"] == "success"
