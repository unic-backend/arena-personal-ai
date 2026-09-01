"""Le connecteur audio : ce qu'il refuse, et ce qu'il vérifie avant de dire oui.

VoiceStudio est un programme **séparé** sous AGPL-3.0 qu'ARENA pilote par
HTTP. Les tests marqués `integration` exigent qu'il tourne ; les autres
doivent tenir sur une machine où il n'y a rien — c'est le cas du CI.

Le test qui compte vraiment est `TestLaVoixNeSortPasDeLaMachine` : une voix
est une donnée sensible, et rien ne doit pouvoir la faire voyager.
"""

import httpx
import pytest

from core.actions.resultat import Statut
from core.connectors.audio_voix import (
    URL_PAR_DEFAUT,
    AdresseNonLocale,
    ConnecteurAudioVoix,
    ErreurDeMoteur,
    sonder_le_fichier,
    url_de_voicestudio,
)


class TestLaVoixNeSortPasDeLaMachine:
    """Règle 3 du module, et la seule qui protège une donnée personnelle."""

    @pytest.mark.parametrize("url", [
        "https://api.exemple.com",
        "http://192.168.1.50:3900",
        "http://voicestudio.example.org:3900",
        "http://0.0.0.0:3900",
    ])
    def test_une_adresse_non_locale_est_refusee(self, monkeypatch, url):
        monkeypatch.setenv("OMNIVOICE_URL", url)
        with pytest.raises(AdresseNonLocale):
            url_de_voicestudio()

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:3900", "http://localhost:3900", "http://[::1]:3900",
    ])
    def test_la_boucle_locale_passe(self, monkeypatch, url):
        monkeypatch.setenv("OMNIVOICE_URL", url)
        assert url_de_voicestudio() == url

    def test_sans_configuration_l_adresse_reste_locale(self, monkeypatch):
        monkeypatch.delenv("OMNIVOICE_URL", raising=False)
        assert url_de_voicestudio() == URL_PAR_DEFAUT
        assert "127.0.0.1" in URL_PAR_DEFAUT

    def test_une_adresse_non_locale_rend_le_connecteur_non_configure(
        self, monkeypatch, tmp_path
    ):
        """Refuser doit se voir dans la santé, pas seulement lever."""
        monkeypatch.setenv("OMNIVOICE_URL", "https://api.exemple.com")
        sante = ConnecteurAudioVoix(dossier=tmp_path).sante()
        assert not sante.utilisable
        assert "api.exemple.com" in sante.message


class TestSansVoiceStudio:
    """La machine du CI n'a pas VoiceStudio. Rien ne doit être simulé."""

    @pytest.fixture
    def injoignable(self, monkeypatch):
        def refuse(*_a, **_k):
            raise httpx.ConnectError("connexion refusée")
        monkeypatch.setattr(httpx.Client, "get", refuse)
        monkeypatch.setattr(httpx.Client, "post", refuse)

    def test_la_sante_dit_ce_qui_manque(self, injoignable, tmp_path):
        sante = ConnecteurAudioVoix(dossier=tmp_path).sante()
        assert not sante.utilisable
        assert "VoiceStudio" in sante.ce_qui_manque
        assert "AGPL" in sante.ce_qui_manque, (
            "le message doit rappeler que c'est un programme séparé"
        )

    def test_aucune_capacite_ne_repond_a_la_place_du_service(self, injoignable, tmp_path):
        c = ConnecteurAudioVoix(dossier=tmp_path)
        for capacite in ("moteurs", "transcrire"):
            r = c.executer(capacite)
            assert r.statut is not Statut.SUCCES, f"{capacite} a inventé une réussite"

    def test_rien_n_est_ecrit_quand_le_service_est_absent(self, injoignable, tmp_path):
        """Un échec ne doit pas laisser un fichier vide derrière lui."""
        dossier = tmp_path / "audio"
        c = ConnecteurAudioVoix(dossier=dossier)
        r = c.executer_confirmee("parler", texte="bonjour")

        assert r.statut is not Statut.SUCCES
        restes = list(dossier.glob("*.wav")) if dossier.exists() else []
        assert restes == [], f"fichier laissé derrière un échec : {restes}"


@pytest.fixture
def service_en_bonne_sante(monkeypatch):
    """VoiceStudio répond — sans qu'il tourne.

    La base lit `sante()` AVANT toute capacité : sans ce double, ces tests
    ne passeraient que sur une machine où VoiceStudio tourne. C'est
    exactement le piège qui a fait rougir le CI sur le connecteur de
    montage (ffmpeg présent ici, absent là-bas) — mesuré le 01/09/2026.
    """
    from core.connectors.base import EtatSante, Sante, _maintenant

    monkeypatch.setattr(
        ConnecteurAudioVoix, "sonder",
        lambda self: Sante(etat=EtatSante.OPERATIONNEL, message="double",
                           mesure_le=_maintenant()))


class TestFichierIntrouvable:
    def test_transcrire_sans_fichier_est_un_echec_nomme(
        self, service_en_bonne_sante, tmp_path
    ):
        c = ConnecteurAudioVoix(dossier=tmp_path)
        r = c.executer("transcrire", chemin=str(tmp_path / "fantome.wav"))
        assert r.statut is Statut.ECHEC
        assert "fantome.wav" in r.message

    def test_parler_sans_texte_est_un_echec(self, service_en_bonne_sante, tmp_path):
        c = ConnecteurAudioVoix(dossier=tmp_path)
        r = c.executer_confirmee("parler", texte="   ")
        assert r.statut is Statut.ECHEC


class TestLaSondeNInventeRien:
    """Un champ absent est None, jamais 0 — la règle du dépôt."""

    def test_un_fichier_absent_ne_rend_aucun_zero(self, tmp_path):
        mesures = sonder_le_fichier(tmp_path / "rien.wav")
        assert mesures == {"duree_ms": None, "octets": None, "format": None}

    def test_un_fichier_qui_n_est_pas_de_l_audio_n_a_pas_de_duree(self, tmp_path):
        faux = tmp_path / "faux.wav"
        faux.write_bytes(b"ceci n'est pas du son")
        mesures = sonder_le_fichier(faux)
        assert mesures["octets"] == 21
        assert mesures["duree_ms"] is None, "une durée inventée sur un fichier illisible"

    def test_une_sonde_absente_ne_fabrique_pas_de_mesure(self, tmp_path):
        fichier = tmp_path / "x.wav"
        fichier.write_bytes(b"x" * 10)
        mesures = sonder_le_fichier(fichier, ffprobe="ffprobe-qui-n-existe-pas")
        assert mesures["duree_ms"] is None


class TestCapacites:
    def test_parler_est_une_ecriture_transcrire_non(self, tmp_path):
        capacites = ConnecteurAudioVoix(dossier=tmp_path).capacites()
        assert capacites["parler"].ecriture is True
        assert capacites["transcrire"].ecriture is False
        assert capacites["moteurs"].ecriture is False

    def test_le_service_est_celui_declare_dans_les_permissions(self, tmp_path):
        assert ConnecteurAudioVoix(dossier=tmp_path).service == "audio_voix"


class TestChoixDuMoteur:
    """VoiceStudio garde un moteur « actif » même absent. ARENA ne le suit pas."""

    def _connecteur(self, tmp_path, disponibles):
        c = ConnecteurAudioVoix(dossier=tmp_path)
        c._moteurs_disponibles = lambda url, genre: list(disponibles)
        return c

    def test_sans_moteur_installe_c_est_non_configure(
        self, service_en_bonne_sante, tmp_path
    ):
        c = self._connecteur(tmp_path, [])
        r = c.executer_confirmee("parler", texte="bonjour")
        assert r.statut is Statut.NON_CONFIGURE
        assert "aucun moteur" in r.message

    def test_un_moteur_demande_mais_absent_est_refuse_et_liste_les_autres(self, tmp_path):
        c = self._connecteur(tmp_path, ["kittentts"])
        with pytest.raises(ErreurDeMoteur) as erreur:
            c._choisir_la_voix("http://127.0.0.1:3900", "omnivoice")
        assert "kittentts" in str(erreur.value)

    def test_le_premier_disponible_est_choisi_pas_le_defaut_du_service(self, tmp_path):
        c = self._connecteur(tmp_path, ["kittentts", "sherpa-onnx"])
        assert c._choisir_la_voix("http://127.0.0.1:3900", "") == "kittentts"


# --- Ce qui exige VoiceStudio en marche ----------------------------------------

def voicestudio_repond() -> bool:
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            return client.get(f"{url_de_voicestudio()}/system/info").status_code == 200
    except Exception:
        return False


@pytest.mark.integration
class TestAvecVoiceStudioReel:
    """Ces tests exigent le vrai VoiceStudio sur 127.0.0.1:3900."""

    @pytest.fixture(autouse=True)
    def exige_le_service(self):
        if not voicestudio_repond():
            pytest.skip("VoiceStudio ne tourne pas sur cette machine.")

    def test_la_sante_est_mesuree_pas_supposee(self, tmp_path):
        sante = ConnecteurAudioVoix(dossier=tmp_path).sante()
        assert sante.utilisable
        assert sante.mesure_le, "une santé sans date n'est pas une mesure"

    def test_les_moteurs_viennent_de_la_machine(self, tmp_path):
        r = ConnecteurAudioVoix(dossier=tmp_path).executer("moteurs")
        assert r.statut in (Statut.SUCCES, Statut.NON_CONFIGURE)
        if r.statut is Statut.SUCCES:
            assert r.detail["tts"] or r.detail["asr"]

    def test_parler_produit_un_fichier_qui_contient_vraiment_du_son(self, tmp_path):
        import struct
        import wave

        c = ConnecteurAudioVoix(dossier=tmp_path)
        r = c.executer_confirmee("parler", langue="en",
                                 texte="UniC Plaquiste builds drywall partitions.")
        if r.statut is Statut.NON_CONFIGURE:
            pytest.skip(f"aucun moteur de voix installé : {r.message}")
        assert r.statut is Statut.SUCCES, r.message

        from pathlib import Path
        fichier = Path(r.preuve)
        assert fichier.exists() and r.detail["duree_ms"] > 500

        with wave.open(str(fichier)) as son:
            brut = son.readframes(son.getnframes())
        echantillons = struct.unpack(f"<{len(brut) // 2}h", brut)
        assert max(abs(e) for e in echantillons) > 1000, (
            "le fichier est du silence : une voix absente s'est fait passer pour une voix"
        )

    def test_le_tour_complet_texte_voix_texte(self, tmp_path):
        """La seule preuve qui vaille : ce qui a été dit se réentend."""
        c = ConnecteurAudioVoix(dossier=tmp_path)
        dit = c.executer_confirmee("parler", langue="en",
                                   texte="We install drywall partitions in Dakar.")
        if dit.statut is not Statut.SUCCES:
            pytest.skip(f"synthèse indisponible : {dit.message}")

        relu = c.executer("transcrire", chemin=dit.preuve, langue="en")
        assert relu.statut is Statut.SUCCES, relu.message
        mots = relu.detail["texte"].lower()
        assert "drywall" in mots and "dakar" in mots, (
            f"la transcription ne correspond pas à ce qui a été dit : {mots}"
        )
