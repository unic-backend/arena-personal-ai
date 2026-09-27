"""Chaîne réelle d'une réunion enregistrée : média -> Whisper -> compte rendu."""

import pytest

from agents.video_analyzer.video_analyzer_agent import VideoAnalyzerAgent


class ProviderReunion:
    def __init__(self):
        self.prompts = []

    async def is_available(self):
        return True

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        return (
            "1. Résumé\nLe devis est validé.\n"
            "2. Points clés\n- Livraison\n"
            "3. Décisions explicites\n- Devis validé\n"
            "4. Actions à faire\n- Fatou envoie le PDF demain\n"
            "5. Questions ouvertes\n- Aucune"
        )


@pytest.mark.asyncio
async def test_un_enregistrement_de_reunion_produit_un_resultat_affichable(
    tmp_path, monkeypatch,
):
    media = tmp_path / "reunion.m4a"
    media.write_bytes(b"audio-test")
    provider = ProviderReunion()
    agent = VideoAnalyzerAgent(provider=provider)

    monkeypatch.setattr(
        agent.ffmpeg,
        "extract_audio",
        lambda source, cible: True,
    )
    segments = [
        {
            "start": 0.0,
            "end": 30.0,
            "text": "Le devis est validé. Fatou envoie le PDF demain.",
        }
    ]
    monkeypatch.setattr(
        agent.transcriber,
        "transcribe",
        lambda chemin: {
            "full_text": "Le devis est validé. Fatou envoie le PDF demain.",
            "duration": 30.0,
            "segments": segments,
        },
    )

    resultat = await agent.run(
        "Fais le compte rendu de cette réunion et donne les actions.",
        {"video_path": str(media)},
    )

    assert resultat["status"] == "success"
    assert resultat["analysis_kind"] == "meeting_transcript_analysis"
    assert resultat["media_name"] == "reunion.m4a"
    assert resultat["transcription_source"] == "whisper_local"
    assert resultat["meeting_metrics"]["duration_seconds"] == 30.0
    assert resultat["meeting_metrics"]["speaker_separation_available"] is False
    assert resultat["response"] == resultat["ai_analysis"]
    assert "Fatou envoie le PDF demain" in resultat["response"]
    assert "Métriques mesurées" in resultat["response"]
    assert "Répartition des locuteurs : non disponible" in resultat["response"]

    prompt, options = provider.prompts[-1]
    assert "UNIQUEMENT" in prompt
    assert "Fatou envoie le PDF demain" in prompt
    assert "N'invente jamais l'identité d'un locuteur" in prompt
    # consulter=False est consommé par BaseAgent.rediger et ne fuit pas
    # comme option inconnue vers le fournisseur.
    assert "consulter" not in options


@pytest.mark.asyncio
async def test_une_analyse_video_ordinaire_garde_son_chemin_existant(
    tmp_path, monkeypatch,
):
    media = tmp_path / "chantier.mp4"
    media.write_bytes(b"video-test")
    provider = ProviderReunion()
    agent = VideoAnalyzerAgent(provider=provider)
    monkeypatch.setattr(agent.ffmpeg, "extract_audio", lambda source, cible: True)
    monkeypatch.setattr(
        agent.transcriber,
        "transcribe",
        lambda chemin: {
            "full_text": "Pose de plaques BA13.",
            "duration": 12.0,
            "segments": [{"start": 0.0, "end": 12.0, "text": "Pose de plaques BA13."}],
        },
    )

    resultat = await agent.run("Analyse cette vidéo.", {"video_path": str(media)})

    assert resultat["status"] == "success"
    assert resultat["analysis_kind"] == "audio_transcription_and_text_analysis"
    assert resultat["meeting_metrics"] is None
    assert "expert en analyse vidéo" in provider.prompts[-1][0]
