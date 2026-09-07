"""Le connecteur audio : ce qu'il refuse, et ce qu'il vérifie avant de dire oui.

VoiceStudio est un programme **séparé** sous AGPL-3.0 qu'ARENA pilote par
HTTP. Les tests marqués `integration` exigent qu'il tourne ; les autres
doivent tenir sur une machine où il n'y a rien — c'est le cas du CI.

Le test qui compte vraiment est `TestLaVoixNeSortPasDeLaMachine` : une voix
est une donnée sensible, et rien ne doit pouvoir la faire voyager.
"""

import shutil
import struct
import wave
from pathlib import Path

import httpx
import pytest

from core.actions.resultat import Statut
from core.connectors.audio_voix import (
    URL_PAR_DEFAUT,
    AdresseNonLocale,
    ConnecteurAudioVoix,
    ErreurDeMoteur,
    ressemble_a_du_wav,
    sonder_le_fichier,
    url_de_voicestudio,
)

#: `ffprobe` n'est pas installé sur le CI. Les mesures qui l'exigent sont
#: sautées là-bas — sauter n'est pas passer, et le rapport le dit.
_SANS_FFPROBE = pytest.mark.skipif(
    shutil.which("ffprobe") is None,
    reason="ffprobe absent : la mesure de durée ne peut pas être faite ici")


def _un_vrai_wav(dossier: Path, secondes: float = 1.0) -> Path:
    """Un WAV réel d'une seconde, écrit sans ffmpeg — le CI n'en a pas."""
    chemin = dossier / "vrai.wav"
    cadence = 8000
    with wave.open(str(chemin), "wb") as flux:
        flux.setnchannels(1)
        flux.setsampwidth(2)
        flux.setframerate(cadence)
        flux.writeframes(struct.pack("<h", 0) * int(cadence * secondes))
    return chemin


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
        assert mesures == {"duree_ms": None, "octets": None, "format": None,
                           "sonde_disponible": None}

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

    def test_une_sonde_absente_se_distingue_d_un_fichier_muet(self, tmp_path):
        """« ffprobe manque » et « ce fichier n'a pas de durée » sont deux
        constats différents. Les confondre a fait jeter un son valide."""
        fichier = tmp_path / "x.wav"
        fichier.write_bytes(b"x" * 10)

        sans_sonde = sonder_le_fichier(fichier, ffprobe="ffprobe-qui-n-existe-pas")

        assert sans_sonde["sonde_disponible"] is False
        if shutil.which("ffprobe"):
            assert sonder_le_fichier(fichier)["sonde_disponible"] is True

    @_SANS_FFPROBE
    def test_le_format_est_vraiment_mesure(self, tmp_path):
        """`ffprobe` rend `format_name` AVANT `duration` : lire « la dernière
        ligne » comme le format laissait ce champ toujours à None."""
        wav = _un_vrai_wav(tmp_path)

        mesures = sonder_le_fichier(wav)

        assert mesures["duree_ms"] == 1000
        assert mesures["format"] == "wav", "le format n'est toujours pas mesuré"


class TestUnSonValideSurvitAUneSondeAbsente:
    """Défaut mesuré le 02/09/2026, et le plus coûteux du module.

    Sans `ffprobe`, `sonder_le_fichier` rend `duree_ms = None` — pour une
    raison qui ne concerne **pas** le fichier. `_parler` traitait ce `None`
    comme « le son est mauvais », supprimait le fichier et annonçait un échec.
    Un WAV réel de 2 s et 176 478 octets partait ainsi à la poubelle.

    La règle 2 du module tient quand même : l'en-tête du conteneur est
    vérifiée, donc un message d'erreur renvoyé avec un code 200 reste refusé.
    Ce qui change, c'est qu'on n'annonce **pas** une durée qu'on n'a pas
    mesurée.
    """

    @staticmethod
    def _connecteur_qui_produit(monkeypatch, contenu: bytes, dossier: Path,
                                sonde_absente: bool = True):
        import core.connectors.audio_voix as module

        connecteur = ConnecteurAudioVoix(dossier=dossier)
        monkeypatch.setattr(connecteur, "_choisir_la_voix", lambda url, demande: "piper")

        class FausseReponse:
            status_code = 200
            content = contenu

        class FauxClient:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, *a, **kw):
                return FausseReponse()

        monkeypatch.setattr(module.httpx, "Client", FauxClient)
        if sonde_absente:
            vraie = module.sonder_le_fichier
            monkeypatch.setattr(
                module, "sonder_le_fichier",
                lambda chemin: vraie(chemin, ffprobe="ffprobe-qui-n-existe-pas"))
        return connecteur

    def test_le_fichier_est_garde_et_le_resultat_est_un_succes(
            self, monkeypatch, tmp_path):
        son = _un_vrai_wav(tmp_path).read_bytes()
        connecteur = self._connecteur_qui_produit(monkeypatch, son, tmp_path / "sortie")

        resultat = connecteur._parler("http://127.0.0.1:3900", texte="bonjour")

        assert resultat.statut is Statut.SUCCES, "un son valide a encore ete jete"
        assert Path(resultat.preuve).is_file()

    def test_la_duree_non_mesuree_n_est_pas_annoncee(self, monkeypatch, tmp_path):
        """Annoncer une durée qu'on n'a pas mesurée serait pire que se taire."""
        son = _un_vrai_wav(tmp_path).read_bytes()
        connecteur = self._connecteur_qui_produit(monkeypatch, son, tmp_path / "sortie")

        resultat = connecteur._parler("http://127.0.0.1:3900", texte="bonjour")

        assert resultat.detail["duree_ms"] is None
        assert "non verifiee" in resultat.message

    def test_une_erreur_en_json_avec_un_code_200_reste_refusee(
            self, monkeypatch, tmp_path):
        """La règle 2 ne s'affaiblit pas : ce n'est pas du son, ça ne passe pas."""
        connecteur = self._connecteur_qui_produit(
            monkeypatch, b'{"error": "modele absent"}', tmp_path / "sortie")

        resultat = connecteur._parler("http://127.0.0.1:3900", texte="bonjour")

        assert resultat.statut is Statut.ECHEC
        assert not list((tmp_path / "sortie").glob("*.wav")), "le faux son a ete garde"

    def test_l_entete_wav_est_reconnue_pour_ce_qu_elle_est(self, tmp_path):
        assert ressemble_a_du_wav(_un_vrai_wav(tmp_path)) is True

        pas_du_son = tmp_path / "faux.wav"
        pas_du_son.write_bytes(b'{"error": "modele absent"}')
        assert ressemble_a_du_wav(pas_du_son) is False


class TestCapacites:
    def test_parler_est_une_ecriture_transcrire_non(self, tmp_path):
        capacites = ConnecteurAudioVoix(dossier=tmp_path).capacites()
        assert capacites["parler"].ecriture is True
        assert capacites["transcrire"].ecriture is False
        assert capacites["moteurs"].ecriture is False

    def test_cloner_est_une_ecriture_distincte_de_parler(self, tmp_path):
        capacites = ConnecteurAudioVoix(dossier=tmp_path).capacites()
        assert capacites["cloner"].ecriture is True
        assert capacites["cloner"].action == "cloner", (
            "l'action doit differer de 'document' : le clonage a son propre "
            "risque dans config/permissions_services.yaml"
        )

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


class TestVoiceDesign:
    """`instruct` : verifie dans le source de VoiceStudio, jamais suppose."""

    def test_instruct_absent_ne_change_rien_au_corps(self, monkeypatch, tmp_path):
        import core.connectors.audio_voix as module

        c = ConnecteurAudioVoix(dossier=tmp_path)
        monkeypatch.setattr(c, "_choisir_la_voix", lambda url, demande: "omnivoice")
        corps_vus = []

        class FauxClient:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, json=None, **kw):
                corps_vus.append(json)
                class R:
                    status_code = 200
                    content = b""
                return R()

        monkeypatch.setattr(module.httpx, "Client", FauxClient)
        c._parler("http://127.0.0.1:3900", texte="bonjour")
        assert "instruct" not in corps_vus[0]

    def test_instruct_fourni_est_transmis_tel_quel(self, monkeypatch, tmp_path):
        import core.connectors.audio_voix as module

        c = ConnecteurAudioVoix(dossier=tmp_path)
        monkeypatch.setattr(c, "_choisir_la_voix", lambda url, demande: "omnivoice")
        corps_vus = []

        class FauxClient:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, json=None, **kw):
                corps_vus.append(json)
                class R:
                    status_code = 200
                    content = b""
                return R()

        monkeypatch.setattr(module.httpx, "Client", FauxClient)
        c._parler("http://127.0.0.1:3900", texte="bonjour",
                  instruct="female, low pitch, british accent")
        assert corps_vus[0]["instruct"] == "female, low pitch, british accent"


class TestChoixDuMoteurPourLeClonage:
    """`supports_cloning` vient de VoiceStudio, jamais suppose (DEC-0065)."""

    def _connecteur(self, tmp_path, backends):
        c = ConnecteurAudioVoix(dossier=tmp_path)
        c._moteurs_capables_de_clonage = lambda url: [
            b["id"] for b in backends if b.get("available") and b.get("supports_cloning") is True
        ]
        return c

    def test_aucun_moteur_capable_leve_une_erreur_nommee(self, tmp_path):
        c = self._connecteur(tmp_path, [
            {"id": "kittentts", "available": True, "supports_cloning": False},
        ])
        with pytest.raises(ErreurDeMoteur) as erreur:
            c._choisir_pour_clonage("http://127.0.0.1:3900", "")
        assert "clonage" in str(erreur.value)

    def test_un_moteur_capable_mais_non_demande_est_choisi(self, tmp_path):
        c = self._connecteur(tmp_path, [
            {"id": "kittentts", "available": True, "supports_cloning": False},
            {"id": "omnivoice", "available": True, "supports_cloning": True},
        ])
        assert c._choisir_pour_clonage("http://127.0.0.1:3900", "") == "omnivoice"

    def test_un_moteur_demande_mais_incapable_est_refuse(self, tmp_path):
        c = self._connecteur(tmp_path, [
            {"id": "kittentts", "available": True, "supports_cloning": False},
            {"id": "omnivoice", "available": True, "supports_cloning": True},
        ])
        with pytest.raises(ErreurDeMoteur) as erreur:
            c._choisir_pour_clonage("http://127.0.0.1:3900", "kittentts")
        assert "kittentts" in str(erreur.value)
        assert "omnivoice" in str(erreur.value)

    def test_supports_cloning_none_ne_compte_pas_comme_prouve(self, tmp_path):
        """Capacite dependant du modele charge (ex. mlx-audio) : pas une preuve."""
        c = self._connecteur(tmp_path, [
            {"id": "mlx-audio", "available": True, "supports_cloning": None},
        ])
        with pytest.raises(ErreurDeMoteur):
            c._choisir_pour_clonage("http://127.0.0.1:3900", "")


class TestLeFiltreDeClonageInterrogeVraimentVoiceStudio:
    """`_moteurs_capables_de_clonage` reel, jamais remplace par un double.

    Les tests de `TestChoixDuMoteurPourLeClonage` remplacent cette methode
    elle-meme : ils prouvent que `_choisir_pour_clonage` l'utilise bien, mais
    pas que SON filtre `supports_cloning` lit vraiment le champ. Un sabotage
    de ce filtre (retirer `and b.get("supports_cloning") is True`) laissait
    ces dix tests passer — cette classe est la, precisement, pour l'attraper.
    """

    def _reponse_engines(self, monkeypatch, backends):
        import core.connectors.audio_voix as module

        class FausseReponse:
            def json(self):
                return {"backends": backends}

        class FauxClient:
            def __init__(self, **kw):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def get(self, url):
                return FausseReponse()

        monkeypatch.setattr(module.httpx, "Client", FauxClient)

    def test_un_moteur_disponible_mais_non_clonant_est_exclu(self, monkeypatch, tmp_path):
        c = ConnecteurAudioVoix(dossier=tmp_path)
        self._reponse_engines(monkeypatch, [
            {"id": "kittentts", "available": True, "supports_cloning": False},
        ])
        assert c._moteurs_capables_de_clonage("http://127.0.0.1:3900") == []

    def test_un_moteur_clonant_et_disponible_est_retenu(self, monkeypatch, tmp_path):
        c = ConnecteurAudioVoix(dossier=tmp_path)
        self._reponse_engines(monkeypatch, [
            {"id": "kittentts", "available": True, "supports_cloning": False},
            {"id": "omnivoice", "available": True, "supports_cloning": True},
        ])
        assert c._moteurs_capables_de_clonage("http://127.0.0.1:3900") == ["omnivoice"]

    def test_un_moteur_clonant_mais_indisponible_est_exclu(self, monkeypatch, tmp_path):
        c = ConnecteurAudioVoix(dossier=tmp_path)
        self._reponse_engines(monkeypatch, [
            {"id": "omnivoice", "available": False, "supports_cloning": True},
        ])
        assert c._moteurs_capables_de_clonage("http://127.0.0.1:3900") == []


class TestClonage:
    """Deux appels reels a VoiceStudio (profil, puis synthese) — jamais un seul."""

    @staticmethod
    def _wav_reel(dossier):
        return _un_vrai_wav(dossier)

    def _connecteur_capable(self, tmp_path, moteur="omnivoice"):
        c = ConnecteurAudioVoix(dossier=tmp_path / "sortie")
        c._choisir_pour_clonage = lambda url, demande: moteur
        return c

    def test_sans_autorisation_rien_n_est_tente(self, tmp_path):
        c = self._connecteur_capable(tmp_path)

        def jamais_appele(url, demande):
            raise AssertionError("le moteur a ete choisi sans autorisation declaree")

        c._choisir_pour_clonage = jamais_appele

        r = c._cloner("http://127.0.0.1:3900", texte="bonjour",
                      ref_audio=str(self._wav_reel(tmp_path)), autorisation="")
        assert r.statut is Statut.ECHEC
        assert "Autorisation" in r.message

    def test_sans_reference_reelle_c_est_un_echec_nomme(self, tmp_path):
        c = self._connecteur_capable(tmp_path)
        r = c._cloner("http://127.0.0.1:3900", texte="bonjour",
                      ref_audio=str(tmp_path / "fantome.wav"),
                      autorisation="Ousmane, proprietaire de la voix")
        assert r.statut is Statut.ECHEC
        assert "fantome.wav" in r.message

    def test_aucun_moteur_capable_est_non_configure(self, tmp_path):
        c = ConnecteurAudioVoix(dossier=tmp_path / "sortie")
        c._choisir_pour_clonage = lambda url, demande: (_ for _ in ()).throw(
            ErreurDeMoteur("aucun moteur disponible dans VoiceStudio ne declare le clonage"))
        r = c._cloner("http://127.0.0.1:3900", texte="bonjour",
                      ref_audio=str(self._wav_reel(tmp_path)),
                      autorisation="Ousmane")
        assert r.statut is Statut.NON_CONFIGURE

    def test_le_clonage_reussi_passe_par_le_profil_puis_la_synthese(self, monkeypatch, tmp_path):
        import core.connectors.audio_voix as module

        c = self._connecteur_capable(tmp_path)
        son = self._wav_reel(tmp_path).read_bytes()
        appels = []

        class FausseReponseProfil:
            status_code = 201
            text = ""
            def json(self):
                return {"id": "profil-abc123"}

        class FausseReponseSynthese:
            status_code = 200
            content = son

        class FauxClient:
            def __init__(self, **kw):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def post(self, url, **kw):
                appels.append((url, kw))
                if url.endswith("/profiles"):
                    return FausseReponseProfil()
                return FausseReponseSynthese()

        monkeypatch.setattr(module.httpx, "Client", FauxClient)

        r = c._cloner("http://127.0.0.1:3900", texte="Bonjour Dakar",
                      ref_audio=str(self._wav_reel(tmp_path)), ref_text="allo",
                      autorisation="Ousmane, proprietaire de la voix")

        assert r.statut is Statut.SUCCES, r.message
        assert len(appels) == 2, "le clonage doit faire deux appels : profil, puis synthese"
        url_profil, kw_profil = appels[0]
        assert url_profil.endswith("/profiles")
        assert kw_profil["data"]["kind"] == "clone"
        assert "ref_audio" in kw_profil["files"]

        url_parole, kw_parole = appels[1]
        assert url_parole.endswith("/v1/audio/speech")
        assert kw_parole["json"]["voice"] == "profil-abc123"

        assert r.detail["profil"] == "profil-abc123"
        assert r.detail["autorisation"] == "Ousmane, proprietaire de la voix"
        assert Path(r.preuve).is_file()

    def test_un_profil_refuse_est_un_echec_et_rien_n_est_ecrit(self, monkeypatch, tmp_path):
        import core.connectors.audio_voix as module

        c = self._connecteur_capable(tmp_path)

        class FausseReponseProfil:
            status_code = 422
            text = "clone profiles require ref_audio"

        class FauxClient:
            def __init__(self, **kw):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def post(self, url, **kw):
                return FausseReponseProfil()

        monkeypatch.setattr(module.httpx, "Client", FauxClient)

        r = c._cloner("http://127.0.0.1:3900", texte="bonjour",
                      ref_audio=str(self._wav_reel(tmp_path)),
                      autorisation="Ousmane")
        assert r.statut is Statut.ECHEC
        assert not list((tmp_path / "sortie").glob("*.wav")), "rien ne devait etre ecrit"

    def test_resultat_attendu_nomme_la_source_et_l_autorisation(self, tmp_path):
        c = ConnecteurAudioVoix(dossier=tmp_path)
        capacite = c.capacites()["cloner"]
        texte = c.resultat_attendu(
            capacite, ref_audio="media/voix_client.wav", autorisation="Fatou, cliente")
        assert "media/voix_client.wav" in texte
        assert "Fatou, cliente" in texte


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
