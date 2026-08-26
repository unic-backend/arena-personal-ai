"""ClipSelectorAgent : choix du meilleur extrait et découpe. Exige ffmpeg et Ollama."""
import pytest

from agents.clip_selector.clip_selector_agent import ClipSelectorAgent

SEGMENTS = [
    {"start": 0.0, "end": 4.0, "text": "Bonjour à tous, bienvenue dans cette vidéo."},
    {"start": 4.0, "end": 12.0, "text": "Aujourd'hui, le plus grand secret de l'innovation au Sénégal !"},
    {"start": 12.0, "end": 18.0, "text": "Merci d'avoir regardé, abonnez-vous."},
]


@pytest.mark.integration
async def test_un_extrait_est_selectionne_et_decoupe(ollama_en_ligne, video_de_test, memoire):
    agent = ClipSelectorAgent(provider=ollama_en_ligne, memory=memoire)

    res = await agent.run(
        "Trouve le meilleur moment viral",
        context={"video_path": str(video_de_test), "segments": SEGMENTS},
    )

    assert res["status"] == "success"
