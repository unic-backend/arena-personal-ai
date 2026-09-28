"""DeepResearcherAgent : plan de recherche, croisement de sources, rapport.

Deux appels au modèle (plan puis synthèse) et une recherche web doublée.
"""
import time

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


async def test_les_trois_requetes_tournent_en_parallele(provider_factory, monkeypatch):
    """La preuve, pas la promesse : trois recherches de 0,3 s doivent tenir en
    un seul intervalle, pas en trois mis bout à bout."""
    DUREE = 0.3
    agent = DeepResearcherAgent(
        provider=provider_factory("un\ndeux\ntrois", "Rapport final."), memory=None)

    def _search_lente(query, max_results=5):
        time.sleep(DUREE)
        return [source(1)]

    monkeypatch.setattr(agent.search_tool, "search", _search_lente)

    debut = time.monotonic()
    await agent.run("Sujet")
    ecoule = time.monotonic() - debut

    assert ecoule < DUREE * 2, (
        f"{ecoule:.2f} s pour trois recherches de {DUREE} s : "
        "elles n'ont pas tourne en parallele")


async def test_sans_aucune_source_aucun_rapport_n_est_redige(agent_avec_web):
    """DEC-0152 : zero page web et zero connaissance locale — le modele n'est
    appele que pour le plan, jamais pour un « rapport » qui serait invente."""
    agent = agent_avec_web([])

    async def rien(*args, **kwargs):
        return []

    agent.knowledge_vault.hybrid_search = rien

    res = await agent.run("Marché du cajou en Casamance")

    assert res["status"] == "warning"
    assert res["sources_count"] == 0
    assert len(agent.provider.appels) == 1, "seul le plan de recherche a appele le modele"
    assert "aucune source" in res["response"]


async def test_la_synthese_ne_peut_citer_que_les_sources_recues(agent_avec_web):
    agent = agent_avec_web([source(3)])

    await agent.run("Sujet")

    consigne = agent.provider.appels[1]["prompt"]
    assert "ne liste QUE ces sources-là" in consigne
    assert "N'ajoute aucun chiffre, nom ou fait" in consigne


async def test_un_chiffre_du_rapport_absent_des_sources_est_signale(agent_avec_web):
    """La consigne de #357 n'etait verifiee par rien (DEC-0158)."""
    rapport = "Le marché sénégalais de l'IA pèse 450 millions [1], selon Gartner."
    agent = agent_avec_web([source(1)], rapport=rapport)

    res = await agent.run("IA au Sénégal")

    assert res["response"].startswith(rapport), "le rapport n'est jamais reecrit"
    assert "Verification automatique" in res["response"]
    assert res["sans_source"] == ["Gartner", "450"]


async def test_un_rapport_fidele_n_est_pas_signale(agent_avec_web):
    rapport = "Contenu de la source 1 [1]. Le sujet IA au Sénégal est couvert par Source 1."
    agent = agent_avec_web([source(1)], rapport=rapport)

    res = await agent.run("IA au Sénégal")

    assert res["response"] == rapport
    assert res["sans_source"] == []
