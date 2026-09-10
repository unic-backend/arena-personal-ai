"""Le connecteur CSM : ce qu'il refuse, et ce qu'il vérifie avant de dire oui.

Meme discipline que `tests/core/test_connecteur_audio.py` (son modele) : le
service CSM est un programme SEPARE, ces tests tiennent sur une machine ou
il n'y a rien — le cas du CI, ou du tout premier lancement local avant que le
proprietaire n'ait installe `tools/audio/csm_service/`.

Le test qui compte le plus ici est `TestLeFiligraneEstVerifie` : un fichier
audio sans provenance verifiable ne doit JAMAIS etre garde.
"""
import struct
import wave
from pathlib import Path

import httpx
import pytest

from core.actions.resultat import Statut
from core.audio.verification import AdresseNonLocale
from core.connectors.csm import (
    IDENTIFIANT,
    URL_PAR_DEFAUT,
    ConnecteurCsm,
    url_du_service,
)


def _un_vrai_wav(dossier: Path, secondes: float = 1.0) -> bytes:
    chemin = dossier / "reel.wav"
    cadence = 8000
    with wave.open(str(chemin), "wb") as flux:
        flux.setnchannels(1)
        flux.setsampwidth(2)
        flux.setframerate(cadence)
        flux.writeframes(struct.pack("<h", 0) * int(cadence * secondes))
    return chemin.read_bytes()


class FausseReponse:
    def __init__(self, status_code=200, json_data=None, content=b"", headers=None,
                text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = content
        self.headers = headers or {}
        self.text = text or str(json_data or "")

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erreur", request=None, response=self)


class FauxClient:
    def __init__(self, reponse_get=None, reponse_post=None, **kw):
        self._get = reponse_get
        self._post = reponse_post

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, *a, **kw):
        if self._get is None:
            raise httpx.ConnectError("connexion refusee")
        return self._get

    def post(self, *a, **kw):
        if self._post is None:
            raise httpx.ConnectError("connexion refusee")
        return self._post


def _patch_client(monkeypatch, *, reponse_get=None, reponse_post=None):
    import core.connectors.csm as module
    monkeypatch.setattr(
        module.httpx, "Client",
        lambda **kw: FauxClient(reponse_get=reponse_get, reponse_post=reponse_post))


class TestLaVoixNeSortPasDeLaMachine:
    @pytest.mark.parametrize("url", [
        "https://api.exemple.com", "http://192.168.1.50:8901",
        "http://csm.example.org:8901",
    ])
    def test_une_adresse_non_locale_est_refusee(self, monkeypatch, url):
        monkeypatch.setenv("CSM_URL", url)
        with pytest.raises(AdresseNonLocale):
            url_du_service()

    def test_sans_configuration_l_adresse_reste_locale(self, monkeypatch):
        monkeypatch.delenv("CSM_URL", raising=False)
        assert url_du_service() == URL_PAR_DEFAUT
        assert "127.0.0.1" in URL_PAR_DEFAUT

    def test_le_port_est_distinct_de_voicestudio_et_wangp(self):
        """3900 (VoiceStudio) et 8765 (WanGP) : trois services locaux coexistent."""
        assert URL_PAR_DEFAUT not in ("http://127.0.0.1:3900", "http://127.0.0.1:8765")


class TestSansServiceCsm:
    def test_la_sante_dit_ce_qui_manque(self, monkeypatch, tmp_path):
        _patch_client(monkeypatch)
        sante = ConnecteurCsm(dossier=tmp_path).sante()
        assert not sante.utilisable
        assert "csm_service" in sante.ce_qui_manque

    def test_aucune_capacite_ne_repond_a_la_place_du_service(self, monkeypatch, tmp_path):
        _patch_client(monkeypatch)
        c = ConnecteurCsm(dossier=tmp_path)
        for capacite in ("moteurs", "parler"):
            r = c.executer(capacite)
            assert r.statut is not Statut.SUCCES


class TestAucuneCapaciteDeClonage:
    """Decision deliberee (`core/connectors/csm.py`) : jamais un second chemin
    de clonage vocal, plus faible que celui — deja consenti — de audio_voix."""

    def test_cloner_n_est_pas_une_capacite_declaree(self):
        capacites = ConnecteurCsm().capacites()
        assert "cloner" not in capacites
        assert set(capacites) == {"moteurs", "parler"}


@pytest.fixture
def service_charge(monkeypatch):
    from core.connectors.base import EtatSante, Sante, _maintenant
    monkeypatch.setattr(
        ConnecteurCsm, "sonder",
        lambda self: Sante(etat=EtatSante.OPERATIONNEL, message="double",
                           mesure_le=_maintenant()))


class TestModeleNonCharge:
    def test_moteurs_est_non_configure_sans_modele_charge(
        self, monkeypatch, service_charge, tmp_path
    ):
        _patch_client(monkeypatch, reponse_get=FausseReponse(
            json_data={"model_loaded": False, "ce_qui_manque": "acces HF gated refuse"}))
        r = ConnecteurCsm(dossier=tmp_path).executer("moteurs")
        assert r.statut is Statut.NON_CONFIGURE
        assert "acces HF gated" in r.message

    def test_la_sante_relaie_le_message_du_service(self, monkeypatch, tmp_path):
        _patch_client(monkeypatch, reponse_get=FausseReponse(
            json_data={"model_loaded": False, "ce_qui_manque": "401 gated"}))
        sante = ConnecteurCsm(dossier=tmp_path).sante()
        assert not sante.utilisable
        assert "401 gated" in sante.ce_qui_manque


class TestMoteurCharge:
    def test_moteurs_rend_l_identifiant_attendu_et_les_langues(
        self, monkeypatch, service_charge, tmp_path
    ):
        _patch_client(monkeypatch, reponse_get=FausseReponse(json_data={
            "model_loaded": True, "device": "cuda:0", "device_is_accelerated": True,
            "watermarking": True}))
        r = ConnecteurCsm(dossier=tmp_path).executer("moteurs")
        assert r.statut is Statut.SUCCES
        assert r.detail["tts"] == [IDENTIFIANT]
        voix = r.detail["voix"][0]
        assert voix["langues"] == ["en"]
        assert voix["conversationnel"] is True

    def test_la_sante_est_operationnelle(self, monkeypatch, tmp_path):
        _patch_client(monkeypatch, reponse_get=FausseReponse(json_data={
            "model_loaded": True, "device": "cpu"}))
        sante = ConnecteurCsm(dossier=tmp_path).sante()
        assert sante.utilisable


class TestParlerSansTexte:
    def test_est_un_echec(self, monkeypatch, service_charge, tmp_path):
        _patch_client(monkeypatch)
        r = ConnecteurCsm(dossier=tmp_path).executer_confirmee("parler", texte="   ")
        assert r.statut is Statut.ECHEC


class TestLeFiligraneEstVerifie:
    """La garantie centrale (mission §12) cote ARENA : ce connecteur ne
    garde JAMAIS un fichier que le service declare lui-meme non filigrane."""

    def test_un_audio_declare_non_filigrane_est_un_echec(
        self, monkeypatch, service_charge, tmp_path
    ):
        wav = _un_vrai_wav(tmp_path)
        dossier = tmp_path / "sortie"
        _patch_client(monkeypatch, reponse_post=FausseReponse(
            status_code=200, content=wav, headers={
                "X-CSM-Device": "cpu", "X-CSM-Watermarked": "false"}))

        r = ConnecteurCsm(dossier=dossier).executer_confirmee("parler", texte="Hello")

        assert r.statut is Statut.ECHEC
        assert "filigrane" in r.message.lower() or "provenance" in r.message.lower()
        assert not list(dossier.glob("*.wav")) if dossier.exists() else True

    def test_un_audio_filigrane_est_garde(self, monkeypatch, service_charge, tmp_path):
        wav = _un_vrai_wav(tmp_path)
        dossier = tmp_path / "sortie"
        _patch_client(monkeypatch, reponse_post=FausseReponse(
            status_code=200, content=wav, headers={
                "X-CSM-Device": "cpu", "X-CSM-Watermarked": "true"}))

        r = ConnecteurCsm(dossier=dossier).executer_confirmee("parler", texte="Hello")

        assert r.statut is Statut.SUCCES
        assert r.detail["filigrane_applique"] is True
        assert list(dossier.glob("*.wav"))


class TestServiceRefuseGenerer:
    def test_409_devient_non_configure(self, monkeypatch, service_charge, tmp_path):
        _patch_client(monkeypatch, reponse_post=FausseReponse(
            status_code=409, json_data={"detail": {"message": "modele non charge"}}))
        r = ConnecteurCsm(dossier=tmp_path).executer_confirmee("parler", texte="Hello")
        assert r.statut is Statut.NON_CONFIGURE
        assert "modele non charge" in r.message

    def test_500_devient_un_echec(self, monkeypatch, service_charge, tmp_path):
        _patch_client(monkeypatch, reponse_post=FausseReponse(
            status_code=500, text="Generation impossible"))
        r = ConnecteurCsm(dossier=tmp_path).executer_confirmee("parler", texte="Hello")
        assert r.statut is Statut.ECHEC


class TestConversationSansFichier:
    """Mission §10/§13 : ce que l'agent transmet ne porte jamais de chemin."""

    def test_les_tours_transmis_ne_contiennent_que_texte_et_locuteur(
        self, monkeypatch, service_charge, tmp_path
    ):
        wav = _un_vrai_wav(tmp_path)
        corps_recus = {}

        class ClientQuiCapture(FauxClient):
            def post(self, url, json=None, **kw):
                corps_recus.update(json or {})
                return FausseReponse(status_code=200, content=wav, headers={
                    "X-CSM-Device": "cpu", "X-CSM-Watermarked": "true"})

        import core.connectors.csm as module
        monkeypatch.setattr(module.httpx, "Client", lambda **kw: ClientQuiCapture())

        ConnecteurCsm(dossier=tmp_path / "sortie").executer_confirmee(
            "parler", texte="Et toi ?", speaker=1,
            conversation=[
                {"texte": "Salut", "speaker": 0, "chemin_fichier_malicieux": "/etc/passwd"},
            ])

        assert corps_recus["conversation"] == [{"texte": "Salut", "speaker": 0}]
        assert "chemin_fichier_malicieux" not in str(corps_recus)
