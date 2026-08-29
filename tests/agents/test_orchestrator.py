"""Orchestrateur : classification de l'intention, repli, et composition de la réponse.

L'aiguillage passe désormais par le modèle rapide. Le fournisseur est scripté :
on choisit ce que « le modèle » répond, y compris quand il répond n'importe quoi.
"""
import pytest

from agents.orchestrator.orchestrator_agent import INTENTIONS, OrchestratorAgent

# Les faux positifs relevés par l'audit : le mot est là, la demande ne l'est pas.
PIEGES_DE_L_AUDIT = [
    "Explique-moi le code de la route",
    "Calcule mon devis",
    "Quelle erreur j'ai faite hier ?",
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

    Sans modèle, « code », « calcule » et « erreur » renvoient toujours vers le
    CoderAgent. C'est la limite connue du repli, pas une régression.
    """
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    assert agent._classer_par_mots_cles(phrase) == "CODE_EXECUTION"


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

    res = await agent.run("Bonjour", context={"session_id": "s1"})

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
