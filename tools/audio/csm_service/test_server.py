"""Tests du service CSM — a lancer dans SON environnement isole, jamais dans
`pytest tests/` d'ARENA (`testpaths = ["tests"]` dans `pyproject.toml` ne
scanne meme pas ce dossier : ce fichier est invisible a la suite principale,
volontairement — ce service depend de `torch`, absent de l'environnement
principal).

    cd tools/audio/csm_service
    pip install -r requirements.txt pytest
    pytest test_server.py -q

Le test le plus important est `TestLeFiligraneNEstJamaisOptionnel` : un
service qui renverrait de l'audio non filigrane romprait la garantie que la
mission Sesame CSM (§12) exige.
"""
import pytest
import server
import torch
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def etat_propre():
    """Chaque test part d'un etat neuf : aucun etat ne fuit entre les tests."""
    server._ETAT.update({
        "processor": None, "modele": None, "device": None,
        "device_is_accelerated": False, "erreur_chargement": None,
        "dernier_usage": None,
    })
    yield
    server._ETAT.update({
        "processor": None, "modele": None, "device": None,
        "device_is_accelerated": False, "erreur_chargement": None,
        "dernier_usage": None,
    })


@pytest.fixture
def client():
    return TestClient(server.app)


class TestHealthNeChargeJamaisLeModele:
    def test_repond_sans_modele_charge(self, client, monkeypatch):
        appele = {"fois": 0}

        def _echoue_si_appele(*_a, **_k):
            appele["fois"] += 1
            raise AssertionError("health() ne doit jamais charger le modele")

        monkeypatch.setattr(server, "_charger_si_besoin", _echoue_si_appele)
        reponse = client.get("/health")

        assert reponse.status_code == 200
        assert reponse.json()["model_loaded"] is False
        assert appele["fois"] == 0

    def test_relaie_l_erreur_de_chargement_precedente(self, client):
        server._ETAT["erreur_chargement"] = "acces gated refuse : 401"
        reponse = client.get("/health")
        assert reponse.json()["ce_qui_manque"] == "acces gated refuse : 401"


class TestGenerateSansModeleDisponible:
    def test_rend_409_avec_le_message_reel(self, client, monkeypatch):
        monkeypatch.setattr(server, "_charger_si_besoin",
                            lambda: "acces Hugging Face gated refuse (401).")
        reponse = client.post("/generate", json={"texte": "Bonjour"})

        assert reponse.status_code == 409
        assert "401" in reponse.json()["detail"]["message"]

    def test_texte_vide_est_refuse_avant_tout_chargement(self, client, monkeypatch):
        appele = {"fois": 0}
        monkeypatch.setattr(server, "_charger_si_besoin",
                            lambda: (appele.__setitem__("fois", appele["fois"] + 1) or None))
        reponse = client.post("/generate", json={"texte": "   "})
        assert reponse.status_code == 400


class TestLeFiligraneNEstJamaisOptionnel:
    """La garantie centrale de la mission (§12). Rien ici ne doit pouvoir la
    contourner : un audio genere sans filigrane verifiable n'est JAMAIS
    renvoye avec un code 200."""

    def _forcer_modele_charge(self, monkeypatch):
        monkeypatch.setattr(server, "_charger_si_besoin", lambda: None)
        monkeypatch.setattr(server, "_decharger_si_inactif", lambda: None)
        server._ETAT["device"] = "cpu"
        monkeypatch.setattr(
            server, "_generer_un_tour",
            lambda texte, speaker, contexte, max_ms: torch.zeros(2400))

    def test_le_filigrane_applique_est_declare_dans_l_entete(self, client, monkeypatch):
        self._forcer_modele_charge(monkeypatch)
        monkeypatch.setattr(server.watermark, "appliquer",
                            lambda audio, sr, device: (audio, sr))

        reponse = client.post("/generate", json={"texte": "Hello"})

        assert reponse.status_code == 200
        assert reponse.headers["X-CSM-Watermarked"] == "true"
        assert reponse.headers["Content-Type"] == "audio/wav"
        assert len(reponse.content) > 44  # plus que le seul en-tete WAV

    def test_un_filigrane_qui_echoue_refuse_la_reponse_jamais_un_200_muet(
        self, client, monkeypatch
    ):
        """SABOTAGE inverse : si ce test echouait, un fichier sans provenance
        partirait avec un code 200 — exactement ce que la mission interdit."""
        self._forcer_modele_charge(monkeypatch)

        def _leve(*_a, **_k):
            raise RuntimeError("silentcipher absent de cet environnement")

        monkeypatch.setattr(server.watermark, "appliquer", _leve)

        reponse = client.post("/generate", json={"texte": "Hello"})

        assert reponse.status_code == 500
        assert "Filigrane" in reponse.json()["detail"]


class TestLeContexteConversationnelNeContientJamaisUnFichier:
    """Mission §10/§13 : le contexte ne grandit qu'avec de l'audio genere par
    CE service, jamais un chemin fourni par l'appelant."""

    def test_chaque_tour_precedent_est_regenere_pas_lu_sur_disque(self, client, monkeypatch):
        monkeypatch.setattr(server, "_charger_si_besoin", lambda: None)
        monkeypatch.setattr(server, "_decharger_si_inactif", lambda: None)
        monkeypatch.setattr(server.watermark, "appliquer",
                            lambda audio, sr, device: (audio, sr))
        server._ETAT["device"] = "cpu"

        appels = []

        def _tour(texte, speaker, contexte, max_ms):
            appels.append((texte, speaker, len(contexte)))
            return torch.zeros(2400)

        monkeypatch.setattr(server, "_generer_un_tour", _tour)

        reponse = client.post("/generate", json={
            "texte": "Et toi ?",
            "speaker": 1,
            "conversation": [
                {"texte": "Salut, ca va ?", "speaker": 0},
                {"texte": "Tres bien, merci.", "speaker": 1},
            ],
        })

        assert reponse.status_code == 200
        # Deux tours de contexte generes, PUIS le tour final — chacun avec
        # un contexte qui grandit d'un cran, jamais un chemin de fichier
        # nulle part dans les arguments recus par `_generer_un_tour`.
        assert [a[2] for a in appels] == [0, 1, 2]
        assert appels[-1][0] == "Et toi ?" and appels[-1][1] == 1

    def test_un_tour_de_conversation_sans_texte_est_ignore(self, client, monkeypatch):
        monkeypatch.setattr(server, "_charger_si_besoin", lambda: None)
        monkeypatch.setattr(server, "_decharger_si_inactif", lambda: None)
        monkeypatch.setattr(server.watermark, "appliquer",
                            lambda audio, sr, device: (audio, sr))
        server._ETAT["device"] = "cpu"

        appels = []
        monkeypatch.setattr(
            server, "_generer_un_tour",
            lambda texte, speaker, contexte, max_ms: (
                appels.append(texte) or torch.zeros(2400)))

        client.post("/generate", json={
            "texte": "Final.",
            "conversation": [{"texte": "   ", "speaker": 0}],
        })

        assert appels == ["Final."]


class TestDechargementParInactivite:
    def test_pas_de_dechargement_avant_le_delai(self, monkeypatch):
        import time
        monkeypatch.setattr(server, "DELAI_DECHARGEMENT_S", 900.0)
        server._ETAT["modele"] = object()
        server._ETAT["dernier_usage"] = time.monotonic()

        server._decharger_si_inactif()

        assert server._ETAT["modele"] is not None

    def test_dechargement_apres_le_delai(self, monkeypatch):
        import time
        monkeypatch.setattr(server, "DELAI_DECHARGEMENT_S", 1.0)
        server._ETAT["modele"] = object()
        server._ETAT["dernier_usage"] = time.monotonic() - 10.0

        server._decharger_si_inactif()

        assert server._ETAT["modele"] is None

    def test_delai_a_zero_ne_decharge_jamais(self, monkeypatch):
        import time
        monkeypatch.setattr(server, "DELAI_DECHARGEMENT_S", 0.0)
        server._ETAT["modele"] = object()
        server._ETAT["dernier_usage"] = time.monotonic() - 999_999

        server._decharger_si_inactif()

        assert server._ETAT["modele"] is not None
