"""Orchestrateur : classification de l'intention, repli, et composition de la réponse.

L'aiguillage passe désormais par le modèle rapide. Le fournisseur est scripté :
on choisit ce que « le modèle » répond, y compris quand il répond n'importe quoi.
"""
import pytest

from agents.orchestrator.orchestrator_agent import INTENTIONS, OrchestratorAgent

# Les faux positifs relevés par l'audit : le mot est là, la demande ne l'est pas.
#: Des phrases ordinaires que les mots-cles generiques attrapaient a tort.
#: Celles qui restent ici n'ont AUCUN mot de son metier : le repli n'a rien
#: pour les distinguer, et c'est la limite assumee du repli.
PIEGES_DE_L_AUDIT = [
    "Explique-moi le code de la route",
    "Quelle erreur j'ai faite hier ?",
]

#: Les memes pieges, mais qui parlent de SON metier. Ceux-la ne sont plus des
#: pieges : mesure du 31/08/2026, « Calcule mon devis » partait a l'execution
#: de code, comme « calcule le faux plafond du plan… » et « chiffre-moi 18
#: parois de 5,40 x 2,50 m » (celle-ci partait meme en CHAT, donc sans sa
#: grille de prix). Le repli consulte desormais les mots du metier AVANT les
#: listes generiques.
PIEGES_QUI_PARLENT_DU_METIER = [
    "Calcule mon devis",
    "calcule le faux plafond du plan /chantiers/A-101.pdf",
    "calcule combien de plaques BA13 pour 40 m2",
    "chiffre-moi 18 parois de 5,40 x 2,50 m",
    "il y a une erreur dans le devis de Fast Group",
]


@pytest.mark.parametrize("etiquette", sorted(INTENTIONS))
async def test_une_etiquette_connue_est_reprise_telle_quelle(provider_factory, etiquette):
    agent = OrchestratorAgent(provider=provider_factory(etiquette), memory=None)

    assert await agent.analyze_intent("peu importe") == etiquette


@pytest.mark.parametrize(
    "reponse_du_modele, attendu",
    [
        ("code_execution", "CODE_EXECUTION"),           # casse ignorée
        ("  CHAT  ", "CHAT"),                            # espaces
        ("Étiquette : DEEP_RESEARCH", "DEEP_RESEARCH"),  # le modèle bavarde
        ("**TREND_SEARCH**", "TREND_SEARCH"),            # mise en forme markdown
        ("CHAT.", "CHAT"),                               # ponctuation collée
    ],
)
async def test_une_reponse_bruitee_reste_exploitable(provider_factory, reponse_du_modele, attendu):
    agent = OrchestratorAgent(provider=provider_factory(reponse_du_modele), memory=None)

    assert await agent.analyze_intent("peu importe") == attendu


@pytest.mark.parametrize("phrase", PIEGES_DE_L_AUDIT)
async def test_les_pieges_de_l_audit_ne_partent_plus_vers_le_coder(provider_factory, phrase):
    """Avec le modèle, c'est lui qui décide : les mots-clés ne s'imposent plus."""
    agent = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)

    assert await agent.analyze_intent(phrase) == "CHAT"


@pytest.mark.parametrize("phrase", PIEGES_DE_L_AUDIT)
def test_le_repli_par_mots_cles_garde_ses_faux_positifs(fake_provider, phrase):
    """Le repli est moins fin, et ce test le dit au lieu de le cacher.

    Sans modèle, « code » et « erreur » dans une phrase qui ne parle pas de son
    métier renvoient toujours vers le CoderAgent. C'est la limite assumée du
    repli, pas une régression : rien dans « explique-moi le code de la route »
    ne permet de le distinguer d'une question de programmation.
    """
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    assert agent._classer_par_mots_cles(phrase) == "CODE_EXECUTION"


@pytest.mark.parametrize("phrase", PIEGES_QUI_PARLENT_DU_METIER)
def test_une_phrase_de_son_metier_ne_part_jamais_a_l_execution_de_code(
    fake_provider, phrase
):
    """Là où aucun modèle n'est joignable, ce repli est le SEUL classificateur.

    Une demande de devis qui part au bac à sable Python ne reçoit ni sa grille
    de prix, ni son calcul de matériaux — elle reçoit une réponse hors sujet.
    """
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    assert agent._classer_par_mots_cles(phrase) == "PLAQUISTE"


async def test_une_reponse_hors_liste_declenche_le_repli(provider_factory):
    agent = OrchestratorAgent(provider=provider_factory("BONJOUR JE SUIS UN MODELE"), memory=None)

    assert await agent.analyze_intent("Ecris un script python") == "CODE_EXECUTION"


async def test_un_modele_injoignable_declenche_le_repli(fake_provider):
    """Le FakeProvider sans réponse scriptée lève : c'est le modèle qui tombe."""
    agent = OrchestratorAgent(provider=fake_provider, memory=None)
    fake_provider._reponses = []

    assert await agent.analyze_intent("Resous l equation x^2 - 5x + 6") == "DEEP_REASONING"


@pytest.mark.parametrize(
    "phrase, attendu",
    [
        ("Bonjour, comment vas-tu ?", "CHAT"),
        ("Ecris un script python pour trier une liste", "CODE_EXECUTION"),
        ("Resous l equation x au carre moins 5x + 6", "DEEP_REASONING"),
        ("Donne-moi une idée de vidéo pour TikTok", "TREND_SEARCH"),
        ("Fais une recherche approfondie sur l IA", "DEEP_RESEARCH"),
        ("Découpe cette vidéo en short vertical", "VIDEO_ANALYSIS"),
        ("Analyse cette photo du chantier", "VISION"),
        ("Parle-moi un peu de mon projet", "CHAT"),
    ],
)
def test_le_repli_aiguille_toujours_les_cas_explicites(fake_provider, phrase, attendu):
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    assert agent._classer_par_mots_cles(phrase) == attendu


@pytest.mark.parametrize(
    "phrase",
    [
        # Mission EXIF & Media Metadata (DEC-0081), §7 ROUTAGE : le routeur
        # doit atteindre VisionAgent (qui porte lui-meme media_metadata)
        # SANS agent ni routeur separe.
        "Donne-moi toutes les informations techniques disponibles sur cette photo.",
        "Analyse complètement cette photo",
        "exif de cette photo",
    ],
)
def test_les_demandes_de_metadonnees_atteignent_vision(fake_provider, phrase):
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    assert agent._classer_par_mots_cles(phrase) == "VISION"


@pytest.mark.parametrize(
    "phrase",
    [
        "Quelle est la dernière version de Python ?",
        "Qui est le président du Sénégal actuellement ?",
        "Quelle est la météo aujourd'hui ?",
        "Quoi de neuf cette semaine ?",
        "Quel est le prix actuel du ciment ?",
    ],
)
def test_le_repli_reconnait_une_question_d_actualite(fake_provider, phrase):
    """Sans modèle, ces tournures doivent tout de même partir vérifier sur le web."""
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    assert agent._classer_par_mots_cles(phrase) == "FRESH_INFO"


@pytest.mark.parametrize("phrase", [
    "j'ai recu combien de mail aujourd'hui",
    "j'ai reçu combien de mails aujourd'hui",
    "combien d'emails j'ai recu",
])
def test_demande_de_courrier_reconnait_les_variantes_avec_combien(fake_provider, phrase):
    """Trouve le 31/08/2026 : ces formulations ne correspondaient a aucune
    entree exacte de COURRIER — la question partait sur FRESH_INFO."""
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    assert agent.demande_de_courrier(phrase) is True


async def test_le_courrier_l_emporte_sur_le_controle_date(provider_factory):
    """« combien de mail aujourd'hui » contient « aujourd'hui »
    (FORMULATIONS_COURANTES) : sans ce controle, la question partirait en
    recherche web plutot que d'ouvrir Gmail. Le modele est scripte pour
    repondre autre chose : s'il etait appele, le test le verrait."""
    agent = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)

    resultat = await agent.analyze_intent("j'ai recu combien de mail aujourd'hui")

    assert resultat == "EMAIL"


async def test_le_courrier_l_emporte_aussi_sur_l_espace(provider_factory):
    """Meme depuis un espace different, verifier son courrier reste EMAIL."""
    agent = OrchestratorAgent(provider=provider_factory("CODE_EXECUTION"), memory=None)

    resultat = await agent.analyze_intent(
        "j'ai recu combien de mail aujourd'hui", espace="code")

    assert resultat == "EMAIL"


def test_une_question_intemporelle_ne_part_pas_chercher_sur_le_web(fake_provider):
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    assert agent._classer_par_mots_cles("Explique-moi ce qu'est une boucle") == "CHAT"


def test_l_etiquette_fresh_info_fait_partie_de_la_liste_fermee():
    assert "FRESH_INFO" in INTENTIONS


async def test_le_prompt_de_classification_decrit_fresh_info(provider_factory):
    provider = provider_factory("CHAT")
    agent = OrchestratorAgent(provider=provider, memory=None)

    await agent.analyze_intent("peu importe")

    prompt = provider.appels[0]["prompt"]
    assert "FRESH_INFO" in prompt
    assert "dernière version" in prompt


async def test_la_demande_de_l_utilisateur_est_bien_celle_qui_est_classee(provider_factory):
    provider = provider_factory("CHAT")
    agent = OrchestratorAgent(provider=provider, memory=None)

    await agent.analyze_intent("Ma demande précise")

    assert "Ma demande précise" in provider.appels[0]["prompt"]


async def test_la_reponse_reprend_ce_que_le_modele_a_produit(provider_factory, memoire):
    provider = provider_factory("CHAT", "  Bonjour Usman, tout va bien.  ")
    agent = OrchestratorAgent(provider=provider, memory=memoire)

    res = await agent.run("Parle-moi de choses interessantes", context={"session_id": "s1"})

    assert res["response"] == "Bonjour Usman, tout va bien."
    assert res["agent"] == "OrchestratorAgent"
    assert res["intent"] == "CHAT"


async def test_une_intention_deja_calculee_n_est_pas_redemandee(provider_factory, memoire):
    """Classer coûte un appel au modèle : le refaire trois fois par message serait absurde."""
    provider = provider_factory("Réponse.")  # une seule réponse : la génération
    agent = OrchestratorAgent(provider=provider, memory=memoire)

    res = await agent.run("Bonjour", context={"session_id": "s1", "intent": "CHAT"})

    assert res["intent"] == "CHAT"
    assert len(provider.appels) == 1


async def test_l_historique_est_transmis_au_modele(provider_factory, memoire):
    memoire.set_fact("user_profile", "owner", "Usman")
    memoire.add_chat_message(session_id="s1", role="user", content="Je m'appelle Usman.")
    memoire.add_chat_message(session_id="s1", role="assistant", content="Enchanté.")
    provider = provider_factory("Tu t'appelles Usman.")
    agent = OrchestratorAgent(provider=provider, memory=memoire)

    await agent.run("Comment je m'appelle ?", context={"session_id": "s1", "intent": "CHAT"})

    prompt_envoye = provider.appels[0]["prompt"]
    assert "Je m'appelle Usman." in prompt_envoye
    assert "Enchanté." in prompt_envoye
    assert prompt_envoye.rstrip().endswith("Usman:")


async def test_sans_memoire_l_agent_repond_quand_meme(provider_factory):
    agent = OrchestratorAgent(provider=provider_factory("Réponse sans mémoire."), memory=None)

    res = await agent.run("Bonjour", context={"intent": "CHAT"})

    assert res["response"] == "Réponse sans mémoire."


class TestRoutageParEspace:
    """VOLET « espaces separes », phase 2 : l'espace choisi dans la PWA route
    directement vers son agent, sans passer par le modele classeur — mais
    jamais avant les deux controles determinstes, qu'un espace ne peut pas
    deviner mieux qu'une phrase ordinaire.
    """

    @pytest.mark.parametrize("espace,attendu", [
        ("code", "CODE_EXECUTION"),
        ("plaquiste", "PLAQUISTE"),
        ("video", "VIDEO_ANALYSIS"),
        ("web", "FRESH_INFO"),
        ("documents", "RAG_DOCS"),
    ])
    async def test_un_espace_connu_route_sans_appeler_le_modele(self, provider_factory, espace, attendu):
        # Aucune reponse scriptee : un appel au modele ferait echouer le test.
        agent = OrchestratorAgent(provider=provider_factory(), memory=None)

        resultat = await agent.analyze_intent("peu importe la phrase", espace=espace)

        assert resultat == attendu

    async def test_un_espace_inconnu_retombe_sur_le_modele(self, provider_factory):
        agent = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)

        assert await agent.analyze_intent(
            "explique-moi comment ça marche", espace="espace-qui-n-existe-pas"
        ) == "CHAT"

    async def test_sans_espace_rien_ne_change(self, provider_factory):
        """Le comportement par defaut (Usman general) est inchange par cette phase."""
        agent = OrchestratorAgent(provider=provider_factory("DEEP_RESEARCH"), memory=None)

        assert await agent.analyze_intent("demontre ce theoreme") == "DEEP_RESEARCH"

    async def test_le_controle_date_l_emporte_sur_l_espace(self, provider_factory):
        """Une question d'actualite reste FRESH_INFO, meme depuis « Usman Coder »."""
        agent = OrchestratorAgent(provider=provider_factory(), memory=None)

        resultat = await agent.analyze_intent("que se passe-t-il aujourd'hui ?", espace="code")

        assert resultat == "FRESH_INFO"

    async def test_la_question_personnelle_l_emporte_sur_l_espace(self, provider_factory):
        """« Qui suis-je » reste CHAT, meme depuis l'espace Video."""
        agent = OrchestratorAgent(provider=provider_factory(), memory=None)

        resultat = await agent.analyze_intent("qui suis-je ?", espace="video")

        assert resultat == "CHAT"


class TestSalutationPure:
    """Regression du 30/08/2026 : une salutation forcait un devis fabrique.

    Le routage direct par espace (VOLET « espaces separes », phase 2) a
    supprime le filet que le classement offrait par accident a « bonjour »
    (jamais un mot-cle metier, donc jamais route chez PlaquisteAgent). Une
    salutation pure doit rester CHAT, quel que soit l'espace ouvert.
    """

    @pytest.mark.parametrize("phrase", [
        "bonjour", "Bonjour", "Bonjour !", "  bonsoir  ", "salut", "salut !",
        "coucou", "merci", "ça va", "ça va ?", "ca va ?", "comment vas-tu",
    ])
    @pytest.mark.parametrize("espace", ["plaquiste", "code", "video", "web", "documents"])
    async def test_une_salutation_reste_chat_quel_que_soit_l_espace(
        self, provider_factory, phrase, espace
    ):
        # Aucune reponse scriptee : ni le modele ni l'agent specialise ne
        # doivent etre appeles pour une salutation.
        agent = OrchestratorAgent(provider=provider_factory(), memory=None)

        assert await agent.analyze_intent(phrase, espace=espace) == "CHAT"

    async def test_une_vraie_demande_n_est_pas_prise_pour_une_salutation(self, provider_factory):
        """« bonjour, » suivi d'une vraie demande route toujours vers l'espace."""
        agent = OrchestratorAgent(provider=provider_factory(), memory=None)

        resultat = await agent.analyze_intent(
            "bonjour, peux-tu me faire un devis pour 20 m2 de cloison ?", espace="plaquiste"
        )

        assert resultat == "PLAQUISTE"

    async def test_la_salutation_pure_l_emporte_meme_sans_espace(self, provider_factory):
        """Usman general n'est pas different : une salutation reste CHAT sans appeler le modele."""
        agent = OrchestratorAgent(provider=provider_factory(), memory=None)

        assert await agent.analyze_intent("bonjour") == "CHAT"


class TestAiguillageDuMontage:
    """« monte la vidéo du chantier » contient « chantier » : sans cette
    intention, elle partait chez l'assistant devis, qui n'a jamais su monter."""

    @pytest.mark.parametrize("phrase", [
        "monte une vidéo avec les photos du chantier",
        "monte-moi un short avec mes rushes",
        "fais le montage de la vidéo de Ouakam",
        "assemble les clips et ajoute mon logo sur la vidéo",
        "mets un titre sur la vidéo du chantier",
        "prépare-moi un plan de montage",
    ])
    def test_une_demande_de_montage_va_au_montage(self, fake_provider, phrase):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == "MONTAGE"

    @pytest.mark.parametrize("phrase,attendu", [
        ("génère une vidéo sur la pose de placo", "VIDEO_ANALYSIS"),
        ("où en est ma vidéo ?", "VIDEO_ANALYSIS"),
        ("fais-moi un devis pour le chantier de Ouakam", "PLAQUISTE"),
    ])
    def test_le_montage_ne_capture_pas_les_voisins(self, fake_provider, phrase, attendu):
        """Générer une vidéo, en suivre une, ou chiffrer un chantier : trois
        demandes distinctes que « vidéo » et « chantier » rapprochent."""
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == attendu


class TestAiguillageDeLAudio:
    """Le son porte les mots des deux voisins : « transcris la vidéo du
    chantier » contient « chantier » (métier) et « vidéo » (montage)."""

    @pytest.mark.parametrize("phrase", [
        "transcris la vidéo du chantier de Ouakam",
        "qu'est-ce qui est dit dans cet enregistrement ?",
        "lis-moi ce texte à voix haute",
        "fais une voix off pour la vidéo du chantier",
        "génère une voix pour la narration",
        "quelles voix sont disponibles ?",
    ])
    def test_une_demande_de_son_va_a_l_audio(self, fake_provider, phrase):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == "AUDIO"

    @pytest.mark.parametrize("phrase,attendu", [
        ("monte une vidéo avec les photos du chantier", "MONTAGE"),
        ("fais-moi un devis pour le chantier de Ouakam", "PLAQUISTE"),
        ("génère une vidéo sur la pose de placo", "VIDEO_ANALYSIS"),
        # ARENA fabrique déjà les sous-titres de bout en bout : l'audio les
        # lui prenait, et le test du studio est tombé le 01/09/2026.
        ("sous-titre ma vidéo", "STUDIO"),
    ])
    def test_l_audio_ne_capture_pas_les_voisins(self, fake_provider, phrase, attendu):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == attendu


class TestLeClonageVocalEstJoignable:
    """DEC-0065 était injoignable — mesuré le 07/09/2026, par la vérification
    qu'il a demandée.

    L'agent audio savait cloner, le connecteur savait cloner, la permission
    existait, un test couvrait chaque morceau — et **aucune phrase du
    propriétaire n'arrivait jusque-là** : « clone cette voix » partait chez le
    PLAQUISTE, « clonage vocal » au CHAT, et « clone ma voix » chez SOCIAL,
    parce que `RESEAUX` contient « ma voix » (son style d'écriture) et passe
    avant l'audio. Exactement le défaut de DEC-0061, sur du code neuf.

    C'est le test qui manquait : il part de la PHRASE, pas de la capacité.
    """

    @pytest.mark.parametrize("phrase", [
        "clone cette voix avec l'autorisation du client",
        "clone la voix de ce client",
        "clonage vocal de cet enregistrement",
        "cloner cette voix pour la narration",
        # Celle-ci partait chez SOCIAL : « ma voix » est un mot des RESEAUX.
        "clone ma voix pour la voix off",
    ])
    def test_une_demande_de_clonage_va_a_l_audio(self, fake_provider, phrase):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == "AUDIO"

    @pytest.mark.parametrize("phrase,attendu", [
        # « clone » seul n'est pas un mot d'audio : cloner un dépôt reste du code.
        ("clone ce dépôt github", "REPO_ENGINEERING"),
        # Son style d'écriture (`tools/social/voix.py`), pas sa parole.
        ("écris ce post avec ma voix", "SOCIAL"),
    ])
    def test_le_clonage_ne_capture_pas_ses_voisins(self, fake_provider, phrase, attendu):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == attendu


class TestLaPreuveFormelleEstJoignable:
    """DEC-0067. La leçon de DEC-0066, appliquée avant qu'elle ne coûte :
    une capacité qu'aucune phrase n'atteint est morte, quels que soient ses
    tests unitaires.

    `DEEP_REASONING` porte déjà « preuve » et « démontre » — la vérification
    formelle est le cas PLUS ÉTROIT, et doit donc passer avant lui, sans
    pour autant lui prendre le calcul ordinaire.
    """

    @pytest.mark.parametrize("phrase", [
        "prouve formellement que 2+2=4",
        "vérifie ce théorème Lean",
        "preuve formelle de cette propriété",
        "vérifie cette preuve",
        "démontre formellement cette inégalité",
        "voici du code lean à vérifier",
    ])
    def test_une_demande_de_preuve_va_a_la_verification_formelle(
        self, fake_provider, phrase
    ):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == "PREUVE_FORMELLE"

    @pytest.mark.parametrize("phrase,attendu", [
        # Le calcul reste au calcul : il n'a jamais eu besoin de Lean.
        ("résous cette équation du second degré", "DEEP_REASONING"),
        ("démontre que la suite converge", "DEEP_REASONING"),
        # Et le métier reste le métier : « prouve-moi » y veut dire « montre-moi ».
        ("prouve-moi que ce devis est juste", "PLAQUISTE"),
    ])
    def test_la_preuve_formelle_ne_capture_pas_ses_voisins(
        self, fake_provider, phrase, attendu
    ):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == attendu


class TestAiguillageDuProjetVideo:
    """DEC-0037 : une phrase composite (« analyse ces photos et fais-en une
    vidéo avec narration ») porte aussi les mots de VISION/AUDIO — sans ce
    contrôle testé en premier, elle capturait un seul de ses morceaux."""

    @pytest.mark.parametrize("phrase", [
        "un projet vidéo complet pour ce chantier",
        "je veux un projet video de A à Z",
        "une vidéo professionnelle avec narration pour ce chantier",
        "vidéo promotionnelle complète du chantier de Ouakam",
        "produis une vidéo complète avec les photos et une narration",
    ])
    def test_une_demande_de_projet_va_au_projet_video(self, fake_provider, phrase):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == "VIDEO_PROJET"

    @pytest.mark.parametrize("phrase,attendu", [
        ("analyse cette photo du chantier", "VISION"),
        ("fais une voix off pour la vidéo du chantier", "AUDIO"),
        ("monte une vidéo avec les photos du chantier", "MONTAGE"),
        ("génère une vidéo sur la pose de placo", "VIDEO_ANALYSIS"),
    ])
    def test_le_projet_video_ne_capture_pas_les_demandes_d_une_seule_capacite(
        self, fake_provider, phrase, attendu,
    ):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == attendu


class TestNommerUnConnecteurLOuvre:
    """Nommer le service doit atteindre le connecteur qui le porte.

    Signale par le proprietaire le 02/09/2026 : « dans mon gmail il ne
    maitrise rien, quand je lui demande d'entrer dans mes discussions il
    refuse de travailler ». Mesure faite avant tout correctif :
    « entre dans mon gmail », « ouvre ma messagerie », « lis mes courriels »,
    « ouvre mon calendrier », « regarde mon tiktok » rendaient TOUS `CHAT`.

    Le connecteur Gmail fonctionnait. Le connecteur agenda fonctionnait.
    Aucune phrase ordinaire ne les appelait : la demande partait au modele
    generaliste, qui n'a aucun acces a la boite et repond donc qu'il ne peut
    pas. **Le refus venait de l'aiguillage, jamais du connecteur.**

    TikTok, lui, n'etait dans aucune liste — alors que c'est l'un des deux
    reseaux de l'entreprise (`config/metier.yaml`).
    """

    @pytest.mark.parametrize("phrase", [
        "entre dans mon gmail",
        "ouvre mon gmail",
        "verifie mon gmail",
        "regarde dans mes discussions gmail",
        "ouvre ma messagerie",
        "y a quoi dans ma messagerie",
        "lis mes courriels",
    ])
    def test_nommer_gmail_ouvre_le_courrier(self, fake_provider, phrase):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)

        assert agent._classer_par_mots_cles(phrase) == "EMAIL"
        # Le controle deterministe passe avant le modele : il doit reconnaitre
        # ces phrases sans qu'aucun modele soit joignable.
        assert agent.demande_de_courrier(phrase) is True

    @pytest.mark.parametrize("phrase", [
        "ouvre mon calendrier",
        "regarde dans mon calendrier",
        "mes rendez-vous",
        "mes rdv de la semaine",
        "mon planning",
        "mon emploi du temps",
    ])
    def test_nommer_son_calendrier_atteint_l_agenda(self, fake_provider, phrase):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)

        assert agent._classer_par_mots_cles(phrase) == "PLAQUISTE"

    @pytest.mark.parametrize("phrase", [
        "regarde mon tiktok",
        "va sur mon instagram",
        "poste sur tiktok",
        "mon compte instagram",
        "combien j'ai de mes abonnes",
    ])
    def test_nommer_son_reseau_atteint_le_social(self, fake_provider, phrase):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)

        assert agent._classer_par_mots_cles(phrase) == "SOCIAL"

    @pytest.mark.parametrize("phrase,attendu", [
        # Le garde-fou ecrit dans le code depuis le 27/08 : ecrire au client
        # appartient a l'assistant metier, qui connait la grille de prix.
        ("ecris un mail au client pour le chantier", "PLAQUISTE"),
        # « pour tiktok » designe la destination d'un fichier, pas le compte.
        # Sans cette distinction, elargir RESEAUX volait les demandes de video.
        ("fais-moi une video pour tiktok", "VIDEO_ANALYSIS"),
        ("Donne-moi une idée de vidéo pour TikTok", "TREND_SEARCH"),
        ("fais un devis pour le chantier de Diamniadio", "PLAQUISTE"),
    ])
    def test_l_elargissement_ne_vole_pas_les_voisins(self, fake_provider, phrase, attendu):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)

        assert agent._classer_par_mots_cles(phrase) == attendu


class TestAiguillageUiGenerate:
    """DEC-0050 : generer le CODE d'une interface, distinct de DESIGN_UI
    (decider a quoi ca doit ressembler, sans rien ecrire)."""

    @pytest.mark.parametrize("phrase", [
        "Crée une interface moderne de tableau de bord pour une entreprise",
        "génère une interface de connexion",
        "code-moi une interface de profil utilisateur",
        "développe une interface pour afficher mes chantiers",
        "génère un tableau de bord avec des statistiques",
        "crée un dashboard pour suivre mes devis",
        "un composant react pour une carte de profil",
        "prototype d'interface pour mon appli",
    ])
    def test_une_demande_de_generation_va_a_ui_generate(self, fake_provider, phrase):
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == "UI_GENERATE"

    @pytest.mark.parametrize("phrase,attendu", [
        ("quelle palette pour mon site vitrine ?", "DESIGN_UI"),
        ("améliore l'ux de cette page", "DESIGN_UI"),
        ("propose-moi une maquette", "DESIGN_UI"),
        ("écris un script python pour trier des fichiers", "CODE_EXECUTION"),
        ("fais-moi un devis pour le chantier de Ouakam", "PLAQUISTE"),
    ])
    def test_ui_generate_ne_capture_pas_les_voisins(self, fake_provider, phrase, attendu):
        """Decider a quoi ca doit ressembler (DESIGN_UI), ecrire un script
        generique (CODE_EXECUTION) et chiffrer un chantier (PLAQUISTE) ne
        sont pas generer le code d'une interface."""
        agent = OrchestratorAgent(provider=fake_provider, memory=None)
        assert agent._classer_par_mots_cles(phrase) == attendu
