"""`/api/speech/transcribe` — la dictée réelle (Faster-Whisper), pas la
reconnaissance gratuite du navigateur.

Le vrai modèle n'est jamais chargé ici (Ollama/Whisper ne sont pas sur cette
machine, `docs/REGLES_DE_TRAVAIL.md`) : un double tient la place de
`video_agent.transcriber`, exactement comme `tests/tools/test_transcription.py`
le fait déjà pour l'outil lui-même.
"""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import speech
from tools.audio.transcription_tool import ModeleAbsent

CLE_DE_TEST = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE_DE_TEST}"}


class TranscripteurDouble:
    """Rend ce qu'on lui dit de rendre, ou se déclare absent — jamais de vrai calcul."""

    def __init__(self, resultat=None, erreur=None):
        self.resultat = resultat if resultat is not None else {"full_text": "bonjour tout le monde"}
        self.erreur = erreur
        self.chemins_recus = []
        self.langues_recues = []

    def transcribe(self, chemin, langue="fr"):
        self.chemins_recus.append(chemin)
        self.langues_recues.append(langue)
        if self.erreur:
            raise self.erreur
        return self.resultat


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


def envoyer(client, contenu=b"faux contenu audio", nom="dictee.webm", langue=None, entetes=ENTETES):
    data = {"langue": langue} if langue else {}
    return client.post(
        "/api/speech/transcribe",
        files={"file": (nom, io.BytesIO(contenu), "audio/webm")},
        data=data,
        headers=entetes,
    )


def test_une_dictee_est_transcrite(client, monkeypatch):
    double = TranscripteurDouble({"full_text": "bonjour tout le monde"})
    monkeypatch.setattr(speech.video_agent, "transcriber", double)

    res = envoyer(client, langue="fr")

    assert res.status_code == 200, res.json()
    assert res.json() == {"text": "bonjour tout le monde"}
    assert double.langues_recues == ["fr"]


def test_la_langue_par_defaut_est_le_francais(client, monkeypatch):
    double = TranscripteurDouble()
    monkeypatch.setattr(speech.video_agent, "transcriber", double)

    envoyer(client)  # pas de `langue` fournie

    assert double.langues_recues == ["fr"]


def test_un_audio_vide_est_refuse(client, monkeypatch):
    double = TranscripteurDouble()
    monkeypatch.setattr(speech.video_agent, "transcriber", double)

    res = envoyer(client, contenu=b"")

    assert res.status_code == 400
    assert double.chemins_recus == [], "un audio vide ne doit jamais atteindre le modele"


def test_un_audio_trop_long_est_refuse(client, monkeypatch):
    monkeypatch.setattr(speech, "TAILLE_MAX_DICTEE", 1024)
    double = TranscripteurDouble()
    monkeypatch.setattr(speech.video_agent, "transcriber", double)

    res = envoyer(client, contenu=b"x" * 5000)

    assert res.status_code == 413
    assert double.chemins_recus == []


def test_modele_absent_se_rapporte_503(client, monkeypatch):
    double = TranscripteurDouble(erreur=ModeleAbsent("faster-whisper n'est pas installe"))
    monkeypatch.setattr(speech.video_agent, "transcriber", double)

    res = envoyer(client)

    assert res.status_code == 503
    assert "faster-whisper" in res.json()["detail"]


def test_une_erreur_de_transcription_se_rapporte_500(client, monkeypatch):
    double = TranscripteurDouble(erreur=RuntimeError("modele en echec"))
    monkeypatch.setattr(speech.video_agent, "transcriber", double)

    res = envoyer(client)

    assert res.status_code == 500


def test_le_fichier_temporaire_disparait_apres_succes(client, monkeypatch):
    double = TranscripteurDouble()
    monkeypatch.setattr(speech.video_agent, "transcriber", double)

    envoyer(client)

    assert len(double.chemins_recus) == 1
    assert not Path(double.chemins_recus[0]).exists(), "le fichier temporaire n'a pas ete efface"


def test_le_fichier_temporaire_disparait_meme_apres_un_echec(client, monkeypatch):
    double = TranscripteurDouble(erreur=RuntimeError("modele en echec"))
    monkeypatch.setattr(speech.video_agent, "transcriber", double)

    envoyer(client)

    assert not Path(double.chemins_recus[0]).exists()


def test_sans_cle_api_est_refuse(client, monkeypatch):
    double = TranscripteurDouble()
    monkeypatch.setattr(speech.video_agent, "transcriber", double)

    res = envoyer(client, entetes={})

    assert res.status_code == 401
    assert double.chemins_recus == []
