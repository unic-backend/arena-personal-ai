import asyncio

import core.agent.base_agent as base_agent
from agents.video.production_agent import VideoProductionAgent


class _Collaborateurs:
    def __init__(self, resultat=None, delai=0.0):
        self.resultat = resultat or {
            "status": "success", "agent": "recherche", "response": "ok"
        }
        self.delai = delai
        self.appels = []

    def connait(self, nom):
        return nom == "recherche"

    async def demander(self, nom, requete, contexte):
        self.appels.append((nom, requete, contexte))
        if self.delai:
            await asyncio.sleep(self.delai)
        return dict(self.resultat)


def _agent(collaborateurs):
    agent = object.__new__(VideoProductionAgent)
    agent.name = "VideoProductionAgent"
    agent.collaborateurs = collaborateurs
    return agent


async def test_video_specialiste_herite_du_budget_anti_boucle():
    """La video herite du meme garde-fou que tous les agents.

    Jusqu'au 26/09/2026 une demande « simple » ne pouvait deleguer qu'a un
    niveau ; le proprietaire a demande une collaboration recursive a
    profondeur configurable (DEC-0145). Le garde-fou est le meme, a la
    profondeur maximale configuree.
    """
    from core.agent.message import PROFONDEUR_MAX

    collaborateurs = _Collaborateurs()
    agent = _agent(collaborateurs)

    resultat = await agent.demander_specialiste(
        "recherche",
        "cherche cette information",
        {
            "_requete_racine": "bonjour",
            "_delegation_chain": [f"agent-{n}" for n in range(PROFONDEUR_MAX)],
        },
    )

    assert resultat["status"] == "error"
    assert "budget" in resultat["response"]
    assert collaborateurs.appels == []


async def test_video_specialiste_herite_du_timeout(monkeypatch):
    collaborateurs = _Collaborateurs(delai=0.05)
    agent = _agent(collaborateurs)
    monkeypatch.setattr(base_agent, "DELAI_SPECIALISTE_SECONDES", 0.001)

    resultat = await agent.demander_specialiste(
        "recherche", "cherche cette information"
    )

    assert resultat["status"] == "error"
    assert resultat["specialiste"] == "recherche"
    assert "delai" in resultat["response"]


async def test_video_specialiste_conserve_son_contexte_metier():
    collaborateurs = _Collaborateurs()
    agent = _agent(collaborateurs)

    resultat = await agent.demander_specialiste(
        "recherche",
        "cherche cette information",
        {"projet": "video"},
    )

    assert resultat["status"] == "success"
    contexte = collaborateurs.appels[0][2]
    assert contexte["origine"] == "video_production"
    assert contexte["projet"] == "video"
    assert contexte["origine_agent"] == "VideoProductionAgent"
