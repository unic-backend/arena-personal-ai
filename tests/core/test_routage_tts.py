"""Le routeur de voix : un seul, et la licence des poids s'y applique.

**Le défaut que ces tests tiennent** (mesuré le 07/09/2026) : le registre de
VoiceStudio (`backend/services/tts_backend.py:2260`, commit `53ff367`) est un
dictionnaire ordonné dont `omnivoice` est la PREMIÈRE entrée, et ARENA prenait
`disponibles[0]`. Les poids d'OmniVoice sont CC-BY-NC — usage commercial
interdit (`LICENSE-NOTICE.md` de VoiceStudio, lu sur cette machine). UniC
Plaquiste est une entreprise, et une voix off de chantier est un usage
commercial.

Autrement dit : la commande que `docs/COMMANDES_PC.md` lui donnait lui-même
(`git pull && uv sync`) faisait d'un modèle non commercial le moteur par
défaut de toutes ses vidéos, en silence.

Ces tests échouent si cette porte se rouvre.
"""
import pytest

from core.audio.routage_tts import (
    LICENCE_INCONNUE,
    LICENCES,
    Commercial,
    ErreurDeMoteur,
    MoteurTTS,
    Usage,
    choisir,
    licence_de,
    moteurs_depuis,
)


def _moteur(identifiant, *, disponible=True, clonage=None, appareil="cpu",
            routage="cpu_only"):
    return MoteurTTS(identifiant=identifiant, disponible=disponible,
                     clonage=clonage, appareil=appareil, routage=routage,
                     gpu_compatible=())


class TestLaLicenceDesPoidsFermeLaPorte:
    """Le cœur de DEC-0069. Rien d'autre dans ce fichier ne compte autant."""

    def test_omnivoice_seul_disponible_ne_parle_pas_pour_un_travail_commercial(self):
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([_moteur("omnivoice")], usage=Usage.COMMERCIAL)

        assert "CC-BY-NC" in str(erreur.value)

    def test_le_refus_dit_quoi_faire_pas_seulement_non(self):
        """Un refus qui n'ouvre aucune porte est un mur, pas une protection."""
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([_moteur("omnivoice")], usage=Usage.COMMERCIAL)

        message = str(erreur.value)
        assert "cosyvoice" in message, "aucun moteur permissif n'est propose"
        assert "non commercial" in message, "la sortie de secours n'est pas dite"

    def test_un_usage_non_commercial_declare_ouvre_omnivoice(self):
        """La licence n'interdit pas tout : elle interdit le commerce."""
        choisi = choisir([_moteur("omnivoice")], usage=Usage.RECHERCHE)

        assert choisi.identifiant == "omnivoice"

    def test_un_moteur_permissif_passe_avant_omnivoice_meme_place_apres(self):
        """La régression exacte : omnivoice gagnait en étant le premier listé."""
        choisi = choisir([_moteur("omnivoice"), _moteur("cosyvoice")],
                         usage=Usage.COMMERCIAL)

        assert choisi.identifiant == "cosyvoice"

    def test_nommer_omnivoice_ne_contourne_pas_la_licence(self):
        """Demander un moteur n'ouvre aucune porte : il est verifie comme les autres."""
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([_moteur("omnivoice"), _moteur("cosyvoice")],
                    usage=Usage.COMMERCIAL, demande="omnivoice")

        assert "commercial" in str(erreur.value)

    def test_la_variante_en_sous_processus_est_le_meme_modele_donc_la_meme_regle(self):
        """Meme poids, meme licence : changer d'emballage ne change pas les droits."""
        with pytest.raises(ErreurDeMoteur):
            choisir([_moteur("omnivoice-subprocess")], usage=Usage.COMMERCIAL)


class TestInconnuNEstPasUneAutorisation:
    def test_un_moteur_absent_du_tableau_est_inconnu_pas_autorise(self):
        assert licence_de("un-moteur-de-2027") is LICENCE_INCONNUE
        assert LICENCE_INCONNUE.commercial is Commercial.INCONNU

    def test_une_licence_etablie_passe_avant_une_licence_inconnue(self):
        """Un fichier produit sous licence non verifiee ne se rattrape pas."""
        choisi = choisir([_moteur("un-moteur-de-2027"), _moteur("kittentts")],
                         usage=Usage.COMMERCIAL)

        assert choisi.identifiant == "kittentts"

    def test_un_moteur_inconnu_reste_utilisable_faute_de_mieux(self):
        """Bloquer l'inconnu ferait taire ARENA sans preuve d'un probleme."""
        choisi = choisir([_moteur("un-moteur-de-2027")], usage=Usage.COMMERCIAL)

        assert choisi.identifiant == "un-moteur-de-2027"
        assert choisi.licence.commercial is Commercial.INCONNU


class TestLeTableauDesLicencesEstSource:
    @pytest.mark.parametrize("identifiant", sorted(LICENCES))
    def test_chaque_entree_porte_sa_source_et_sa_licence(self, identifiant):
        """Une affirmation juridique sans source se fait effacer par le suivant."""
        licence = LICENCES[identifiant]

        assert len(licence.source) > 20, f"{identifiant} n'a pas de source"
        # « MIT » fait trois caracteres : le seuil est >= 3, pas > 3.
        assert len(licence.licence) >= 3, f"{identifiant} ne nomme pas sa licence"

    def test_la_famille_omnivoice_n_est_jamais_autorisee_par_erreur(self):
        """Les trois emballages d'OmniVoice partagent les memes poids."""
        for identifiant in ("omnivoice", "omnivoice-subprocess", "omnivoice-gguf"):
            assert LICENCES[identifiant].commercial is not Commercial.AUTORISE, (
                f"{identifiant} vient d'etre declare commercialisable")


class TestCeQueLaMachineMesureVientDeLaMachine:
    """Disponibilité, clonage, appareil : lus dans `/engines/tts`, jamais écrits."""

    def test_les_champs_reels_de_voicestudio_sont_lus(self):
        moteurs = moteurs_depuis({"backends": [
            {"id": "cosyvoice", "available": True, "supports_cloning": True,
             "effective_device": "cuda:0", "routing_status": "accelerated",
             "gpu_compat": ["cuda", "cpu"]},
        ]})

        assert moteurs[0].appareil == "cuda:0"
        assert moteurs[0].accelere is True
        assert moteurs[0].gpu_compatible == ("cuda", "cpu")

    def test_un_champ_absent_reste_none_jamais_une_valeur_plausible(self):
        moteurs = moteurs_depuis({"backends": [{"id": "kittentts", "available": True}]})

        assert moteurs[0].appareil is None
        assert moteurs[0].routage is None
        assert moteurs[0].clonage is None
        assert moteurs[0].accelere is False, "aucune mesure ne doit valoir « accelere »"

    def test_un_moteur_sans_identifiant_est_ignore_pas_devine(self):
        assert moteurs_depuis({"backends": [{"available": True}]}) == []

    def test_une_reponse_vide_ne_fabrique_aucun_moteur(self):
        assert moteurs_depuis({}) == []


class TestLAccelerationDepartageAValeurEgale:
    """La seule mesure de latence qu'ARENA obtienne sans faire parler le moteur."""

    def test_un_moteur_accelere_passe_avant_un_moteur_sur_processeur(self):
        choisi = choisir([
            _moteur("kittentts", routage="cpu_only"),
            _moteur("cosyvoice", routage="accelerated", appareil="cuda:0"),
        ], usage=Usage.COMMERCIAL)

        assert choisi.identifiant == "cosyvoice"

    def test_l_acceleration_ne_rachete_jamais_une_licence_interdite(self):
        """Un GPU ne donne aucun droit d'usage commercial."""
        choisi = choisir([
            _moteur("omnivoice", routage="accelerated", appareil="cuda:0"),
            _moteur("kittentts", routage="cpu_only"),
        ], usage=Usage.COMMERCIAL)

        assert choisi.identifiant == "kittentts"

    def test_un_repli_processeur_n_est_pas_une_acceleration(self):
        """`cpu_fallback` = compatible GPU mais tourne sur le processeur."""
        assert _moteur("cosyvoice", routage="cpu_fallback").accelere is False


class TestLesAutresFiltres:
    def test_un_moteur_indisponible_n_est_jamais_choisi(self):
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([_moteur("cosyvoice", disponible=False)], usage=Usage.COMMERCIAL)

        assert "non installe" in str(erreur.value)

    def test_le_voice_design_exige_un_moteur_qui_honore_instruct(self):
        """`instruct` envoye a un moteur qui l'ignore produit une voix quelconque."""
        choisi = choisir([_moteur("kittentts"), _moteur("cosyvoice")],
                         usage=Usage.COMMERCIAL, voice_design=True)

        assert choisi.identifiant == "cosyvoice"
        assert LICENCES["kittentts"].voice_design is False

    def test_sans_moteur_du_tout_le_message_le_dit_simplement(self):
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([], usage=Usage.COMMERCIAL)

        assert "aucun moteur de voix installe" in str(erreur.value)

    def test_un_moteur_nomme_mais_inexistant_liste_ceux_qui_existent(self):
        with pytest.raises(ErreurDeMoteur):
            choisir([_moteur("kittentts")], demande="piper")


class TestSesameCsmLangueEtConversationnel:
    """DEC-0080 : CSM ne concourt QUE pour l'anglais conversationnel demande.

    Rien ici ne doit changer le comportement mesure par les classes
    ci-dessus quand `langue`/`conversationnel` ne sont pas fournis — c'est
    exactement ce que les 38 tests deja presents dans ce fichier verifient
    en continuant a passer sans modification.
    """

    def test_csm_est_dans_le_tableau_avec_sa_source(self):
        licence = LICENCES["sesame-csm-1b"]
        assert licence.commercial is Commercial.AUTORISE
        assert "Apache-2.0" in licence.licence
        assert licence.langues == frozenset({"en"})
        assert licence.conversationnel is True
        assert len(licence.source) > 20

    def test_csm_est_ecarte_pour_le_francais_meme_seul_disponible(self):
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([_moteur("sesame-csm-1b")], usage=Usage.COMMERCIAL, langue="fr")
        assert "en" in str(erreur.value)

    def test_csm_est_ecarte_pour_le_wolof(self):
        with pytest.raises(ErreurDeMoteur):
            choisir([_moteur("sesame-csm-1b")], usage=Usage.COMMERCIAL, langue="wo")

    def test_nommer_csm_en_francais_ne_contourne_pas_la_restriction_de_langue(self):
        """Meme regle que pour la licence : nommer un moteur n'ouvre aucune porte."""
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([_moteur("sesame-csm-1b"), _moteur("cosyvoice")],
                    usage=Usage.COMMERCIAL, langue="fr", demande="sesame-csm-1b")
        assert "sesame-csm-1b" in str(erreur.value)

    def test_csm_reste_eligible_en_anglais(self):
        choisi = choisir([_moteur("sesame-csm-1b")], usage=Usage.COMMERCIAL, langue="en")
        assert choisi.identifiant == "sesame-csm-1b"

    def test_langue_vide_ne_restreint_rien_meme_pour_csm(self):
        """Aucune langue demandee = aucune verification a faire, pour personne."""
        choisi = choisir([_moteur("sesame-csm-1b")], usage=Usage.COMMERCIAL, langue="")
        assert choisi.identifiant == "sesame-csm-1b"

    def test_un_moteur_sans_restriction_de_langue_n_est_jamais_ecarte_par_elle(self):
        """`langues=None` (tous les moteurs VoiceStudio) = pas de verification."""
        choisi = choisir([_moteur("cosyvoice")], usage=Usage.COMMERCIAL, langue="wo")
        assert choisi.identifiant == "cosyvoice"

    def test_csm_passe_devant_un_moteur_generaliste_si_conversationnel_demande(self):
        """La force reelle de CSM (mission §3/§4) : dialogue anglais."""
        choisi = choisir(
            [_moteur("cosyvoice", routage="accelerated", appareil="cuda:0"),
             _moteur("sesame-csm-1b", routage="cpu_only")],
            usage=Usage.COMMERCIAL, langue="en", conversationnel=True)
        assert choisi.identifiant == "sesame-csm-1b"

    def test_csm_ne_passe_pas_devant_par_defaut_sans_demande_conversationnelle(self):
        """Ne PAS faire concourir CSM avec les autres GPU pour du travail ordinaire."""
        choisi = choisir(
            [_moteur("cosyvoice", routage="accelerated", appareil="cuda:0"),
             _moteur("sesame-csm-1b", routage="cpu_only")],
            usage=Usage.COMMERCIAL, langue="en", conversationnel=False)
        assert choisi.identifiant == "cosyvoice"

    def test_la_langue_normalise_les_variantes_regionales(self):
        """`fr-FR`, `FR`, `en-US` : seule la racine de langue compte."""
        choisi = choisir([_moteur("sesame-csm-1b")], usage=Usage.COMMERCIAL, langue="en-US")
        assert choisi.identifiant == "sesame-csm-1b"
        with pytest.raises(ErreurDeMoteur):
            choisir([_moteur("sesame-csm-1b")], usage=Usage.COMMERCIAL, langue="FR-fr")
