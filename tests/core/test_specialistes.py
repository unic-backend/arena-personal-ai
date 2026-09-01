"""Les méthodes de spécialistes : aucune ne doit être décorative.

La consigne du propriétaire tient en une phrase : *« Do not create agents
that only exist as markdown files but cannot actually be invoked by ARENA. »*

`test_chaque_specialiste_a_un_chemin_d_execution_reel` est le test qui la
porte. Il échoue si quelqu'un ajoute au catalogue un métier qu'ARENA ne sait
pas exécuter — ce qui est exactement la façon dont ce genre de système
pourrit : on ajoute des noms, personne ne vérifie qu'ils mènent quelque part.
"""
import pytest

from core.specialistes.catalogue import CATALOGUE, par_identifiant
from core.specialistes.selection import MAXIMUM, RENFORT_PAR_INTENTION, bloc_de_methode, choisir


class TestAucunSpecialisteDecoratif:
    """Chaque méthode doit mener à quelque chose qui existe déjà dans ARENA."""

    @pytest.mark.parametrize("specialiste", CATALOGUE, ids=lambda s: s.identifiant)
    def test_chaque_specialiste_a_un_chemin_d_execution_reel(self, specialiste):
        from agents.orchestrator.orchestrator_agent import OrchestratorAgent

        intentions = OrchestratorAgent.INTENTIONS if hasattr(
            OrchestratorAgent, "INTENTIONS") else None
        if intentions is None:
            import inspect
            import re
            source = inspect.getsource(
                __import__("agents.orchestrator.orchestrator_agent",
                           fromlist=["x"]))
            intentions = set(re.findall(r'"([A-Z_]{3,})"', source))

        assert specialiste.capacite in intentions, (
            f"« {specialiste.identifiant} » pointe vers « {specialiste.capacite} », "
            "qui n'est pas une intention qu'ARENA sait aiguiller : ce spécialiste "
            "serait décoratif"
        )

    @pytest.mark.parametrize("specialiste", CATALOGUE, ids=lambda s: s.identifiant)
    def test_chaque_specialiste_porte_une_methode_et_des_controles(self, specialiste):
        assert specialiste.methode, "une méthode vide n'apprend rien au modèle"
        assert specialiste.controles, "sans contrôles, rien n'est vérifié"
        assert specialiste.fini_quand.strip()

    @pytest.mark.parametrize("specialiste", CATALOGUE, ids=lambda s: s.identifiant)
    def test_fini_quand_est_observable_pas_une_promesse(self, specialiste):
        """« C'est fini quand c'est bien fait » ne veut rien dire."""
        vagues = ("de qualité", "bien fait", "satisfaisant", "professionnel",
                  "optimal", "excellent")
        fini = specialiste.fini_quand.lower()
        assert not any(mot in fini for mot in vagues), (
            f"« {specialiste.fini_quand} » n'est pas vérifiable"
        )

    def test_aucun_identifiant_en_double(self):
        identifiants = [s.identifiant for s in CATALOGUE]
        assert len(identifiants) == len(set(identifiants))

    def test_chaque_renfort_designe_un_specialiste_qui_existe(self):
        """Une intention pointant vers un identifiant mort serait silencieuse."""
        for intention, identifiant in RENFORT_PAR_INTENTION.items():
            assert par_identifiant(identifiant) is not None, (
                f"l'intention {intention} renvoie vers « {identifiant} », absent du catalogue"
            )


class TestOnNeConvoquePersonneSansRaison:
    """Le vrai risque n'est pas d'en manquer un : c'est d'en appeler six."""

    @pytest.mark.parametrize("phrase", [
        "bonjour", "quelle heure est-il ?", "merci", "ça va ?",
        "raconte-moi une blague",
    ])
    def test_une_phrase_ordinaire_n_appelle_aucune_methode(self, phrase):
        assert choisir(phrase) == []

    def test_une_demande_vide_n_appelle_rien(self):
        assert choisir("") == [] and choisir("   ") == []

    @pytest.mark.parametrize("phrase", [
        "audit de sécurité, tests, architecture, SEO, contenu, devis, vidéo",
        "sécurité vulnérabilité injection test couverture architecture devops",
    ])
    def test_le_plafond_tient_meme_sur_une_demande_qui_nomme_tout(self, phrase):
        assert len(choisir(phrase)) <= MAXIMUM

    def test_le_bloc_est_vide_quand_aucune_methode_ne_s_applique(self):
        assert bloc_de_methode([]) == "", "un bloc vide serait du bruit dans chaque prompt"


class TestLeBonMetierEstChoisi:
    @pytest.mark.parametrize("phrase,attendu", [
        ("fais un audit de sécurité du code", "securite"),
        ("il y a une injection SQL possible ici", "securite"),
        ("écris les tests de non-régression", "tests"),
        ("améliore le référencement de mon site", "seo"),
        ("comment être trouvé sur Google", "seo"),
        ("écris une publication pour LinkedIn", "contenu"),
        ("fais-moi un devis pour ce chantier", "affaires"),
        ("monte une vidéo verticale", "media"),
        ("quelle architecture pour ce module", "architecture"),
        ("optimise cette requête SQL", "donnees"),
        ("vérifie cette information à la source", "recherche"),
        ("le déploiement Docker échoue", "devops"),
        ("le bouton ne s'affiche pas sur mobile", "frontend"),
        ("qu'est-ce que je fais en priorité", "produit"),
    ])
    def test_la_demande_appelle_le_metier_attendu(self, phrase, attendu):
        choisis = [s.identifiant for s in choisir(phrase)]
        assert attendu in choisis, f"« {phrase} » a donné {choisis}"

    def test_l_accent_ne_change_pas_le_choix(self):
        assert choisir("securite") == choisir("sécurité")

    def test_l_intention_renforce_quand_les_mots_ne_disent_rien(self):
        """« corrige ce bug » ne nomme aucun métier ; l'aiguilleur, si."""
        assert choisir("corrige ça") == []
        assert [s.identifiant for s in choisir("corrige ça", "SWE_FIX")] == ["tests"]

    def test_un_vrai_mot_passe_devant_le_renfort(self):
        choisis = [s.identifiant for s in choisir("audit de sécurité", "SWE_FIX")]
        assert choisis[0] == "securite"


class TestLeBlocDeMethode:
    def test_il_porte_les_etapes_les_controles_et_la_fin(self):
        bloc = bloc_de_methode(choisir("audit de sécurité du code"))
        assert "Comment procéder" in bloc
        assert "Ce que tu vérifies" in bloc
        assert "C'est fini quand" in bloc

    def test_il_rappelle_qu_ARENA_reste_ARENA(self):
        """Une méthode n'est pas un personnage : la consigne du propriétaire."""
        bloc = bloc_de_methode(choisir("audit de sécurité"))
        assert "Tu restes ARENA" in bloc

    def test_deux_metiers_donnent_deux_sections(self):
        from core.specialistes.catalogue import CATALOGUE as tout
        bloc = bloc_de_methode(list(tout[:2]))
        assert bloc.count("Comment procéder") == 2


class TestLePromptSysteme:
    """Le branchement, pas seulement le catalogue."""

    def test_le_prompt_reste_court_sans_specialiste(self):
        from apps.backend.prompts import prompt_avec_methode

        court = prompt_avec_methode("bonjour")
        long = prompt_avec_methode("fais un audit de sécurité")
        assert len(long) > len(court)
        assert "MÉTHODE DE SPÉCIALISTE" not in court

    def test_la_methode_vient_apres_les_regles_d_arena(self):
        """Une méthode ne doit pas pouvoir effacer ce qu'ARENA s'interdit."""
        from apps.backend.prompts import get_arena_system_prompt, prompt_avec_methode

        complet = prompt_avec_methode("fais un audit de sécurité")
        assert complet.startswith(get_arena_system_prompt())


class TestLesMotsDeTousLesJoursNeDeclenchentRien:
    """« devis » et « chantier » sont les mots ordinaires du propriétaire.

    Mesuré le 01/09/2026 : « corrige ce bug dans le module de devis »
    convoquait la méthode de chiffrage, et « monte une vidéo du chantier »
    aussi. Un déclencheur qui répond au décor plutôt qu'à l'intention gonfle
    le prompt sans rien apporter — même défaut que « ci » reconnu dans
    « merci ».
    """

    @pytest.mark.parametrize("phrase,interdit", [
        ("corrige ce bug dans le module de devis", "affaires"),
        ("monte une vidéo du chantier", "affaires"),
        ("le fichier devis_pdf.py ne compile pas", "affaires"),
        ("écris une publication sur mon chantier", "affaires"),
    ])
    def test_le_decor_n_appelle_pas_le_chiffrage(self, phrase, interdit):
        assert interdit not in [s.identifiant for s in choisir(phrase)]

    @pytest.mark.parametrize("phrase", [
        "fais un devis pour cette cloison",
        "chiffrer 48 m2 de placo",
        "quelle marge sur ce chantier",
        "combien ça coûte en matériaux",
    ])
    def test_l_argent_et_les_quantites_l_appellent_bien(self, phrase):
        assert "affaires" in [s.identifiant for s in choisir(phrase)]

    def test_l_intention_plaquiste_reste_le_filet(self):
        """Quand les mots ne suffisent pas, l'aiguilleur sait déjà."""
        assert [s.identifiant for s in choisir("prépare ça pour le client",
                                               "PLAQUISTE")] == ["affaires"]


class TestLesHuitScenariosDuProprietaire:
    """Les huit cas qu'il a demandé de tester, figés ici."""

    @pytest.mark.parametrize("demande,intention,attendu", [
        ("corrige ce bug dans le module de devis", "SWE_FIX", {"tests"}),
        ("vérifie à la source ce que dit cette documentation", "DEEP_RESEARCH",
         {"recherche"}),
        ("fais une revue de sécurité de ce code", "REPO_ENGINEERING",
         {"securite", "architecture"}),
        ("améliore le référencement de mon site", None, {"seo"}),
        ("audit de sécurité et tests du module de paiement", None,
         {"securite", "tests"}),
        ("écris une publication sur le référencement de mon site", None,
         {"seo", "contenu"}),
        ("monte une vidéo verticale du chantier avec voix off", "MONTAGE",
         {"media"}),
        ("bonjour, comment vas-tu ?", None, set()),
    ])
    def test_le_scenario_choisit_ce_qu_il_doit(self, demande, intention, attendu):
        assert {s.identifiant for s in choisir(demande, intention)} == attendu

    def test_le_cas_multi_domaine_reste_dans_le_plafond(self):
        """« SEO + contenu » est une vraie collaboration ; six ne le serait pas."""
        choisis = choisir("écris une publication sur le référencement de mon site")
        assert 1 < len(choisis) <= MAXIMUM

    def test_chaque_scenario_mobilise_des_outils_qui_existent(self):
        """Un outil nommé mais absent d'ARENA serait décoratif lui aussi."""
        connus = {
            "gitleaks", "ruff", "pytest", "bac_a_sable", "recherche_web",
            "navigateur", "devis", "opentakeoff", "montage", "audio", "ffmpeg",
        }
        for specialiste in CATALOGUE:
            inconnus = set(specialiste.outils) - connus
            assert not inconnus, (
                f"« {specialiste.identifiant} » nomme des outils qu'ARENA n'a pas : "
                f"{sorted(inconnus)}"
            )
