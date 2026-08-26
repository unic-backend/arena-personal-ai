"""DeepResearcherAgent : plan de recherche, croisement de sources, rapport.

Deux appels au modèle (plan puis synthèse) et une recherche web doublée.
"""
import pytest

from agents.researcher.researcher_agent import DeepResearcherAgent


def source(numero: int, url: str = None) -> dict:
    return {
        "title": f"Source {numero}",
        "href": url or f"https://exemple.sn/{numero}",
        "body": f"Contenu de la source {numero}.",
    }


@pytest.fixture
def agent_avec_web(provider_factory, monkeypatch):
    def _creer(par_requete, plan="mot-clé un\nmot-clé deux\nmot-clé trois", rapport="Rapport final."):
        agent = DeepResearcherAgent(provider=provider_factory(plan, rapport), memory=None)
        appels = []

        def _search(query, max_results=5):
            appels.append(query)
            return par_requete(query) if callable(par_requete) else par_requete

        monkeypatch.setattr(agent.search_tool, "search", _search)
        agent.requetes_lancees = appels
        return agent
    return _creer


async def test_le_plan_du_modele_devient_les_requetes_web(agent_avec_web):
    agent = agent_avec_web([source(1)])

    res = await agent.run("IA au Sénégal")

    assert res["queries_used"] == ["mot-clé un", "mot-clé deux", "mot-clé trois"]
    assert agent.requetes_lancees == ["mot-clé un", "mot-clé deux", "mot-clé trois"]


async def test_le_plan_est_limite_a_trois_requetes(agent_avec_web):
    agent = agent_avec_web([source(1)], plan="un\ndeux\ntrois\nquatre\ncinq")

    res = await agent.run("Sujet")

    assert len(res["queries_used"]) == 3


async def test_un_plan_vide_retombe_sur_la_demande_initiale(agent_avec_web):
    agent = agent_avec_web([source(1)], plan="   \n  \n")

    res = await agent.run("IA au Sénégal")

    assert res["queries_used"] == ["IA au Sénégal"]


async def test_les_sources_en_double_sont_comptees_une_fois(agent_avec_web):
    """Les trois requêtes ramènent la même URL : elle ne doit compter que pour une."""
    agent = agent_avec_web([source(1, "https://exemple.sn/identique")])

    res = await agent.run("Sujet")

    assert res["sources_count"] == 1


async def test_les_sources_sont_transmises_au_modele_de_synthese(agent_avec_web):
    agent = agent_avec_web([source(7, "https://exemple.sn/7")])

    await agent.run("Sujet")

    prompt_synthese = agent.provider.appels[1]["prompt"]
    assert "Source 7" in prompt_synthese
    assert "https://exemple.sn/7" in prompt_synthese
