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
