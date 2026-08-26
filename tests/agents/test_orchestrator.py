"""Orchestrateur : l'aiguillage des demandes, et la réponse qu'il compose.

L'aiguillage se fait par mots-clés, sans appel au modèle : il se teste hors ligne.
La composition de la réponse passe par le fournisseur, ici scripté.
"""
import pytest

from agents.orchestrator.orchestrator_agent import OrchestratorAgent

# (phrase de l'utilisateur, intention attendue)
CAS_D_AIGUILLAGE = [
    ("Bonjour, comment vas-tu ?", "CHAT"),
    ("Ecris un script python pour trier une liste", "CODE_EXECUTION"),
    ("Resous l equation x au carre moins 5x + 6", "DEEP_REASONING"),
    ("Donne-moi une idée de vidéo pour TikTok", "TREND_SEARCH"),
    ("Fais une recherche approfondie sur l IA", "DEEP_RESEARCH"),
    ("Découpe cette vidéo en short vertical", "VIDEO_ANALYSIS"),
    # Un mot courant ne doit pas déclencher un agent spécialisé :
    ("Parle-moi un peu de mon projet", "CHAT"),
]


@pytest.mark.parametrize("phrase, attendu", CAS_D_AIGUILLAGE)
async def test_l_aiguillage_designe_le_bon_agent(fake_provider, phrase, attendu):
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    assert await agent.analyze_intent(phrase) == attendu


async def test_l_aiguillage_n_appelle_pas_le_modele(fake_provider):
    """Il est annoncé instantané : un appel au modèle le rendrait faux."""
    agent = OrchestratorAgent(provider=fake_provider, memory=None)

    await agent.analyze_intent("Ecris un script python")

    assert fake_provider.appels == []


async def test_la_reponse_reprend_ce_que_le_modele_a_produit(provider_factory, memoire):
    provider = provider_factory("  Bonjour Saer, tout va bien.  ")
    agent = OrchestratorAgent(provider=provider, memory=memoire)

    res = await agent.run("Bonjour", context={"session_id": "s1"})

    assert res["response"] == "Bonjour Saer, tout va bien."
    assert res["agent"] == "OrchestratorAgent"
    assert res["intent"] == "CHAT"


async def test_l_historique_est_transmis_au_modele(provider_factory, memoire):
    memoire.set_fact("user_profile", "owner", "Saer")
    memoire.add_chat_message(session_id="s1", role="user", content="Je m'appelle Saer.")
    memoire.add_chat_message(session_id="s1", role="assistant", content="Enchanté.")
    provider = provider_factory("Tu t'appelles Saer.")
    agent = OrchestratorAgent(provider=provider, memory=memoire)

    await agent.run("Comment je m'appelle ?", context={"session_id": "s1"})

    prompt_envoye = provider.appels[0]["prompt"]
    assert "Je m'appelle Saer." in prompt_envoye
    assert "Enchanté." in prompt_envoye
    assert prompt_envoye.rstrip().endswith("ARENA:")


async def test_sans_memoire_l_agent_repond_quand_meme(provider_factory):
    """La mémoire est optionnelle : son absence ne doit pas faire tomber l'agent."""
    agent = OrchestratorAgent(provider=provider_factory("Réponse sans mémoire."), memory=None)

    res = await agent.run("Bonjour")

    assert res["response"] == "Réponse sans mémoire."
