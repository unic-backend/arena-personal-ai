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
        """Les trois emballages d'OmniVoice partagent les memes poids.

        **Ce test demandait `is not AUTORISE`, et c'etait trop faible.**
        `INCONNU` satisfait cette assertion — et la regle 4 SERT un moteur
        `INCONNU` en usage commercial. Le test portait donc un nom de
        garde-fou (« n'est jamais autorisee par erreur ») en laissant passer
        exactement ce qu'il pretendait empecher : mesure du 15/09/2026,
        `omnivoice-gguf` etait `INCONNU`, et `choisir(...)` le rendait pour un
        travail commercial. Il exige maintenant `INTERDIT`, qui est le seul
        etat que le routeur ecarte vraiment.
        """
        for identifiant in ("omnivoice", "omnivoice-subprocess", "omnivoice-gguf"):
            assert LICENCES[identifiant].commercial is Commercial.INTERDIT, (
                f"{identifiant} ne porte plus INTERDIT : les memes poids "
                "CC-BY-NC deviendraient servables par cet emballage-la")


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


class TestAudiocppLeSecondPiegeDeLicence:
    """`audiocpp` — le même défaut qu'OmniVoice, apparu six jours plus tard.

    L'amont a bougé : au commit `eaf8bb9` (v0.5.2, lu le 13/09/2026)
    `_LAZY_REGISTRY` porte un moteur qui n'existait pas au relevé du
    07/09/2026. `audiocpp` sert **Breeze-TTS-2**, dont les poids sont
    « research and non-commercial use only » — et la source amont ajoute la
    phrase qui tranche : *« Self-hosted outputs inherit the restriction »*.
    L'audio PRODUIT hérite de la restriction.

    Mesure du 13/09/2026, **avant** cette entrée : `choisir([audiocpp])` en
    usage commercial rendait `audiocpp`, là où le même appel sur `omnivoice`
    refusait. Le moteur tombait sur `LICENCE_INCONNUE`, et la règle 4 laisse
    passer `INCONNU` — délibérément, pour qu'ARENA ne se taise pas devant un
    moteur neuf. C'est donc le tableau qu'il fallait corriger, pas la règle.
    """

    def test_audiocpp_ne_parle_pas_pour_un_travail_commercial(self):
        """Le test qui tient la correction."""
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([_moteur("audiocpp")], usage=Usage.COMMERCIAL, langue="en")

        assert "audiocpp" in str(erreur.value)
        assert "non-commercial" in str(erreur.value)

    def test_il_reste_joignable_pour_un_travail_de_recherche(self):
        """La porte de la règle 3 ne se referme pas : interdit ≠ inexistant."""
        choisi = choisir([_moteur("audiocpp")], usage=Usage.RECHERCHE, langue="en")

        assert choisi.identifiant == "audiocpp"

    def test_un_moteur_permissif_le_remplace_sans_que_l_appelant_choisisse(self):
        """Le repli : la licence écarte, elle ne fait pas taire ARENA."""
        choisi = choisir([_moteur("audiocpp"), _moteur("cosyvoice")],
                         usage=Usage.COMMERCIAL, langue="en")

        assert choisi.identifiant == "cosyvoice"
        assert choisi.licence.commercial is Commercial.AUTORISE

    def test_il_est_ecarte_du_francais_car_ses_langues_sont_mesurees(self):
        """`en` + `zh` d'après la source amont. Le français n'en fait pas
        partie, et la raison du refus le nomme."""
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([_moteur("audiocpp")], usage=Usage.RECHERCHE, langue="fr")

        assert "fr" in str(erreur.value)

    def test_sa_licence_porte_sa_propre_source_pas_celle_du_reste_du_tableau(self):
        """Les autres entrées viennent du commit `53ff367` ; celle-ci d'un
        commit plus récent. Les fondre sous une seule étiquette ferait mentir
        la provenance de l'une des deux."""
        licence = licence_de("audiocpp")

        assert licence.commercial is Commercial.INTERDIT
        assert "eaf8bb9" in licence.source
        assert "53ff367" not in licence.source

    def test_il_n_est_plus_inconnu(self):
        """Le sabotage le plus direct : retirer l'entrée doit faire tomber
        ce test, parce que le moteur redeviendrait `INCONNU` — donc servable
        en commercial."""
        assert licence_de("audiocpp") is not LICENCE_INCONNUE
        assert "audiocpp" in LICENCES


class TestOmnivoiceGgufLeTroisiemePiegeDeLicence:
    """`omnivoice-gguf` — le meme defaut, une troisieme fois.

    Apres `omnivoice` (poids CC-BY-NC) et `audiocpp` (poids BreezeBlue), la
    quantification GGUF d'OmniVoice. Elle etait `INCONNU` depuis le
    07/09/2026, et c'etait honnete a cette date : le derive ne disait pas ses
    termes, et une quantification PEUT relicencier.

    Ce n'est plus vrai. Mesure du 15/09/2026 sur la fiche de
    `Serveurperso/OmniVoice-GGUF` (modifiee le 09/09/2026, donc apres le
    releve) : `license: cc-by-nc-4.0`, et un `license_link` qui pointe la
    section `#license` de `k2-fsa/OmniVoice`. Le quantificateur declare
    lui-meme heriter. Le README du modele de base tranche : *« The pre-trained
    model is licensed under the CC-BY-NC due to constraints from its training
    data »*.

    Ce que ce piege apprend, et que les deux premiers n'avaient pas montre :
    **`INCONNU` n'est pas un etat stable**. Il vieillit. Un « non verifie »
    ecrit un jour reste dans le tableau quand l'amont, lui, a publie ses
    termes — et pendant ce temps le routeur sert le moteur.
    """

    def test_il_ne_parle_plus_pour_un_travail_commercial(self):
        """Le test qui tient la correction."""
        with pytest.raises(ErreurDeMoteur) as erreur:
            choisir([_moteur("omnivoice-gguf")], usage=Usage.COMMERCIAL)

        assert "omnivoice-gguf" in str(erreur.value)
        assert "CC-BY-NC" in str(erreur.value)

    def test_il_reste_joignable_pour_un_travail_de_recherche(self):
        """Interdit n'est pas inexistant : la porte de la regle 3 tient."""
        choisi = choisir([_moteur("omnivoice-gguf")], usage=Usage.RECHERCHE)

        assert choisi.identifiant == "omnivoice-gguf"

    def test_un_moteur_permissif_le_remplace_sans_que_l_appelant_choisisse(self):
        choisi = choisir([_moteur("omnivoice-gguf"), _moteur("voxcpm2")],
                         usage=Usage.COMMERCIAL)

        assert choisi.identifiant == "voxcpm2"
        assert choisi.licence.commercial is Commercial.AUTORISE

    def test_les_trois_emballages_refusent_identiquement(self):
        """Memes poids, meme refus. C'est la propriete qui manquait : avant
        le 15/09/2026 deux emballages refusaient et le troisieme servait."""
        for identifiant in ("omnivoice", "omnivoice-subprocess", "omnivoice-gguf"):
            with pytest.raises(ErreurDeMoteur):
                choisir([_moteur(identifiant)], usage=Usage.COMMERCIAL)

    def test_sa_licence_porte_la_source_qui_l_a_corrigee(self):
        """Elle ne vient plus du README de VoiceStudio mais de la fiche du
        modele. Fondre les deux ferait mentir la provenance."""
        licence = licence_de("omnivoice-gguf")

        assert licence.commercial is Commercial.INTERDIT
        assert "HuggingFace" in licence.source
        assert "15/09/2026" in licence.source


class TestCeQueLaFicheDuModeleACorrige:
    """Trois entrees que la colonne « License » du README decrivait mal.

    Aucune ne changeait un verdict — c'est precisement pour cela qu'elles
    pouvaient rester fausses longtemps. Un tableau de licences dont les
    phrases ne correspondent pas aux verdicts finit par faire corriger le
    verdict pour qu'il colle a la phrase.
    """

    def test_kittentts_documente_ses_poids_pas_son_code(self):
        """VoiceStudio ecrit « MIT » (le code). Les poids de
        `KittenML/kitten-tts-mini-0.8` sont Apache-2.0."""
        licence = licence_de("kittentts")

        assert licence.commercial is Commercial.AUTORISE
        assert "Apache-2.0" in licence.licence
        assert "MIT" in licence.licence, "la licence du code reste nommee"

    def test_supertonic3_ne_dit_plus_le_contraire_de_son_verdict(self):
        """« restrictions d'usage, pas de commerce » se lisait comme une
        interdiction, sous un verdict `AUTORISE`. L'Attachment A du LICENSE
        n'a aucune clause commerciale."""
        licence = licence_de("supertonic3")

        assert licence.commercial is Commercial.AUTORISE
        assert "pas de commerce" not in licence.licence
        assert "interdit le commerce" in licence.licence

    def test_sesame_distingue_l_acces_de_l_usage(self):
        """La fiche est passee `gated`. C'est une condition d'obtention, pas
        une restriction d'usage commercial — les confondre ferait refuser un
        moteur utilisable."""
        licence = licence_de("sesame-csm-1b")

        assert licence.commercial is Commercial.AUTORISE
        assert "Apache-2.0" in licence.licence
        assert "acces sous condition" in licence.licence
