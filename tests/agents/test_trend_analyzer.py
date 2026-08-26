"""TrendAnalyzerAgent : synthèse de tendances à partir de résultats web.

La recherche web est remplacée par un double : aucun appel réseau ne part d'ici.
"""
import pytest

from agents.trend_analyzer.trend_analyzer_agent import TrendAnalyzerAgent

RESULTATS_WEB = [
    {"title": "Startups à Dakar", "href": "https://exemple.sn/1", "body": "Levée de fonds record."},
    {"title": "IA au Sénégal", "href": "https://exemple.sn/2", "body": "Un centre de calcul ouvre."},
]


@pytest.fixture
def agent_avec_web(provider_factory, monkeypatch):
    """Fabrique un agent dont la recherche web renvoie des résultats choisis."""
    def _creer(resultats, reponse_ia="Trois tendances : A, B, C."):
        agent = TrendAnalyzerAgent(provider=provider_factory(reponse_ia), memory=None)
        monkeypatch.setattr(agent.search_tool, "search", lambda query, max_results=5: resultats)
        return agent
    return _creer


async def test_la_synthese_reprend_la_reponse_du_modele(agent_avec_web):
    agent = agent_avec_web(RESULTATS_WEB)

    res = await agent.run("Tech et innovation", context={"region": "Sénégal"})

    assert res["status"] == "success"
    assert res["region"] == "Sénégal"
    assert res["web_sources_count"] == 2
    assert res["response"] == "Trois tendances : A, B, C."


async def test_les_resultats_web_sont_transmis_au_modele(agent_avec_web):
    agent = agent_avec_web(RESULTATS_WEB)

    await agent.run("Tech", context={"region": "Sénégal"})

    prompt = agent.provider.appels[0]["prompt"]
    assert "Startups à Dakar" in prompt
    assert "Levée de fonds record." in prompt


async def test_sans_resultat_web_l_agent_le_dit_et_n_appelle_pas_le_modele(agent_avec_web):
    """Une synthèse sans source serait inventée : l'agent doit s'arrêter avant."""
    agent = agent_avec_web([])

    res = await agent.run("Sujet introuvable")

    assert res["status"] == "warning"
    assert res["agent"].startswith("TrendAnalyzer")
    assert agent.provider.appels == []


async def test_la_region_par_defaut_est_appliquee_sans_contexte(agent_avec_web):
    agent = agent_avec_web(RESULTATS_WEB)

    res = await agent.run("Tech")

    assert res["region"] == "Sénégal & Afrique"
