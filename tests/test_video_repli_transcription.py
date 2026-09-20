"""Le repli de transcription : une capacité joignable vaut mieux qu'un échec.

Mesuré le 01/09/2026 : sur une machine sans `faster_whisper`, l'analyse
vidéo s'arrêtait sur « Transcription impossible » **pendant que VoiceStudio,
qui sait transcrire, répondait sur la boucle locale**. Deux moteurs
existaient, aucun des deux n'était utilisé.

Le repli reste un repli : le chemin normal est le modèle local, qui ne
dépend d'aucun autre programme.
"""
import pytest

from agents.video_analyzer.video_analyzer_agent import VideoAnalyzerAgent
from core.actions.resultat import echec, non_configure, succes
from tools.audio.transcription_tool import ModeleAbsent


class RegistreDouble:
    def __init__(self, resultat):
        self.resultat, self.appels = resultat, []

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, parametres))
        return self.resultat


class ModeleDouble:
    async def is_available(self):
        return True


def agent(registre=None):
    return VideoAnalyzerAgent(provider=ModeleDouble(), registre=registre)


class TestLeRepli:
    def test_sans_registre_il_n_y_a_pas_de_repli(self):
        assert agent(None)._transcrire_par_le_connecteur("/tmp/x.wav") is None

    def test_le_texte_de_voicestudio_est_rendu(self):
        registre = RegistreDouble(succes(
            action="transcrire", cible="audio", message="ok", preuve="p",
            texte="on pose la cloison demain"))
        assert (agent(registre)._transcrire_par_le_connecteur("/tmp/x.wav")
                == "on pose la cloison demain")

    @pytest.mark.parametrize("resultat", [
        non_configure(action="transcrire", cible="audio",
                      ce_qui_manque="VoiceStudio ne repond pas"),
        echec(action="transcrire", cible="audio", message="rien entendu"),
    ])
    def test_un_repli_qui_echoue_rend_none_jamais_un_texte(self, resultat):
        """Une transcription fabriquée serait pire que pas de transcription."""
        assert agent(RegistreDouble(resultat))._transcrire_par_le_connecteur("/x") is None

    def test_le_repli_passe_bien_par_le_connecteur_audio(self):
        registre = RegistreDouble(succes(action="transcrire", cible="audio",
                                         message="ok", preuve="p", texte="x"))
        agent(registre)._transcrire_par_le_connecteur("/tmp/chantier.wav")
        connecteur, capacite, parametres = registre.appels[0]
        assert (connecteur, capacite) == ("audio", "transcrire")
        assert parametres["chemin"] == "/tmp/chantier.wav"


class TestLeCheminNormalNeChangePas:
    def test_le_modele_local_reste_le_premier_appele(self, monkeypatch):
        """Le repli ne doit pas devenir le chemin par défaut."""
        registre = RegistreDouble(succes(action="transcrire", cible="audio",
                                         message="ok", preuve="p", texte="secours"))
        a = agent(registre)
        monkeypatch.setattr(a.transcriber, "transcribe",
                            lambda chemin: {"full_text": "modele local"})

        # Le modèle local répond : le connecteur ne doit pas être sollicité.
        assert a.transcriber.transcribe("/x")["full_text"] == "modele local"
        assert registre.appels == []

    def test_le_modele_absent_est_bien_ce_qui_declenche_le_repli(self):
        """`ModeleAbsent` est l'exception que le repli attrape, pas une autre."""
        assert issubclass(ModeleAbsent, RuntimeError)


class ProviderAnalyse:
    def __init__(self):
        self.prompts = []

    async def is_available(self):
        return True

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return "analyse verifiee"


def agent_analyse(registre=None):
    return VideoAnalyzerAgent(provider=ProviderAnalyse(), registre=registre)


def preparer_video(agent_video, tmp_path, monkeypatch):
    video = tmp_path / "chantier.mp4"
    video.write_bytes(b"video-test")
    monkeypatch.setattr(agent_video.ffmpeg, "extract_audio", lambda source, cible: True)
    return video


@pytest.mark.asyncio
async def test_run_local_preserve_duree_et_segments(tmp_path, monkeypatch):
    a = agent_analyse()
    video = preparer_video(a, tmp_path, monkeypatch)
    segments = [{"start": 0.0, "end": 1.5, "text": "bonjour"}]
    monkeypatch.setattr(a.transcriber, "transcribe", lambda chemin: {
        "full_text": "bonjour chantier", "duration": 1.5, "segments": segments,
    })

    resultat = await a.run("analyse", {"video_path": str(video)})

    assert resultat["status"] == "success"
    assert resultat["transcription_source"] == "whisper_local"
    assert resultat["duration"] == 1.5
    assert resultat["segments"] == segments
    assert resultat["metadata_unavailable"] == []


@pytest.mark.asyncio
async def test_run_fallback_success_est_utilisable_sans_metadonnees_inventees(tmp_path, monkeypatch):
    registre = RegistreDouble(succes(action="transcrire", cible="audio",
                                     message="ok", preuve="p", texte="texte secours"))
    a = agent_analyse(registre)
    video = preparer_video(a, tmp_path, monkeypatch)

    def absent(chemin):
        raise ModeleAbsent("whisper absent")

    monkeypatch.setattr(a.transcriber, "transcribe", absent)
    resultat = await a.run("analyse", {"video_path": str(video)})

    assert resultat["status"] == "success"
    assert resultat["transcription"] == "texte secours"
    assert resultat["transcription_source"] == "voicestudio"
    assert resultat["duration"] is None
    assert resultat["segments"] is None
    assert resultat["metadata_unavailable"] == ["duration", "segments"]
    assert resultat["ai_analysis"] == "analyse verifiee"


@pytest.mark.asyncio
async def test_run_fallback_failure_rend_erreur_sans_analyse(tmp_path, monkeypatch):
    registre = RegistreDouble(non_configure(action="transcrire", cible="audio",
                                            ce_qui_manque="VoiceStudio absent"))
    a = agent_analyse(registre)
    video = preparer_video(a, tmp_path, monkeypatch)

    def absent(chemin):
        raise ModeleAbsent("whisper absent")

    monkeypatch.setattr(a.transcriber, "transcribe", absent)
    resultat = await a.run("analyse", {"video_path": str(video)})

    assert resultat["status"] == "error"
    assert "Transcription impossible" in resultat["response"]
    assert a.provider.prompts == []


@pytest.mark.asyncio
async def test_run_transcription_vide_est_refusee_honnetement(tmp_path, monkeypatch):
    a = agent_analyse()
    video = preparer_video(a, tmp_path, monkeypatch)
    monkeypatch.setattr(a.transcriber, "transcribe", lambda chemin: {
        "full_text": "   ", "duration": None, "segments": None,
    })

    resultat = await a.run("analyse", {"video_path": str(video)})

    assert resultat["status"] == "error"
    assert "aucun texte exploitable" in resultat["response"]
    assert resultat["duration"] is None
    assert resultat["segments"] is None
    assert a.provider.prompts == []
