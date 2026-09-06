"""`/api/contexte/rechercher` — la recherche unifiée réellement atteignable.

Même discipline que `tests/test_hermes_evolution_router.py` : vérifie que la
route atteint vraiment `core.context.recherche_unifiee.rechercher_unifie`,
pas un double indépendant qui pourrait diverger silencieusement.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import contexte_unifie

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def test_la_route_exige_la_cle(client):
    res = client.post("/api/contexte/rechercher", json={"question": "où est cette fonction ?"})
    assert res.status_code == 401


def test_la_route_atteint_reellement_la_recherche_unifiee(client, entetes, monkeypatch):
    appels = []

    async def double(question, **kw):
        appels.append((question, kw))
        return {"status": "success", "sources_interrogees": ["code"], "resultats": [], "response": "ok"}

    monkeypatch.setattr(contexte_unifie, "rechercher_unifie", double)

    res = client.post(
        "/api/contexte/rechercher", json={"question": "où est le contrôle de permission ?"},
        headers=entetes)

    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert appels[0][0] == "où est le contrôle de permission ?"
    assert appels[0][1]["chemin_code"]  # défaut : le dépôt d'ARENA lui-même
    assert appels[0][1]["registre"] is contexte_unifie.registre
    assert appels[0][1]["fresh_info_agent"] is contexte_unifie.fresh_agent

def test_un_chemin_code_explicite_est_transmis(client, entetes, monkeypatch):
    appels = []

    async def double(question, **kw):
        appels.append(kw)
        return {"status": "warning", "sources_interrogees": [], "resultats": [], "response": "rien"}

    monkeypatch.setattr(contexte_unifie, "rechercher_unifie", double)

    client.post(
        "/api/contexte/rechercher",
        json={"question": "où est cette fonction ?", "chemin_code": "/autre/depot", "session_id": "s-1"},
        headers=entetes)

    assert appels[0]["chemin_code"] == "/autre/depot"
    assert appels[0]["session_id"] == "s-1"
