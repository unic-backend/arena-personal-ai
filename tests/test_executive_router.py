"""`/api/executive` — mission ARENA x OPENEXECUTIVE (DEC-0086).

Meme discipline que `tests/test_image_generation_router.py` : la route
atteint reellement `executive_agent.run`, jamais un double independant qui
rejouerait sa propre logique.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import executive

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def test_analyser_exige_la_cle(client):
    res = client.post("/api/executive/analyser", json={"question": "Devrions-nous accepter ?"})
    assert res.status_code == 401


def test_analyser_atteint_reellement_l_agent(client, entetes, monkeypatch):
    appels = []

    async def double(question, **kwargs):
        appels.append(question)
        return {"status": "success", "agent": "ExecutiveAgent", "response": "ok",
                "executive_decision": {"question": question}}

    monkeypatch.setattr(executive.executive_agent, "run", double)

    res = client.post("/api/executive/analyser",
                      json={"question": "Devrions-nous accepter ce chantier ?"},
                      headers=entetes)

    assert res.status_code == 200
    assert appels == ["Devrions-nous accepter ce chantier ?"]
    assert res.json()["executive_decision"]["question"] == "Devrions-nous accepter ce chantier ?"


def test_une_exception_de_l_agent_devient_une_erreur_500_pas_un_crash_muet(client, entetes, monkeypatch):
    async def casse(question, **kwargs):
        raise RuntimeError("modele indisponible")

    monkeypatch.setattr(executive.executive_agent, "run", casse)

    res = client.post("/api/executive/analyser", json={"question": "x"}, headers=entetes)

    assert res.status_code == 500
    assert "modele indisponible" in res.json()["detail"]


def test_roles_rend_le_catalogue_reel(client, entetes):
    res = client.get("/api/executive/roles", headers=entetes)
    assert res.status_code == 200
    identifiants = {r["id"] for r in res.json()["roles"]}
    assert identifiants == {
        "finance", "operations", "risque", "approvisionnement",
        "strategie_marche", "ressources_humaines",
    }


def test_roles_exige_la_cle(client):
    res = client.get("/api/executive/roles")
    assert res.status_code == 401
