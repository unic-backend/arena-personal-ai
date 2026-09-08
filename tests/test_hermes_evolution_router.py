"""`/api/hermes-evolution/evoluer` — le point d'entree reel du connecteur.

Meme discipline que `tests/test_video_production_router.py` (DEC-0037) :
verifie que la route atteint vraiment `registre.executer`, pas un double
independant qui pourrait diverger silencieusement.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import hermes_evolution
from core.actions.resultat import a_confirmer, echec, succes

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def test_la_route_exige_la_cle(client):
    res = client.post(
        "/api/hermes-evolution/evoluer",
        json={"depot_cible": "/tmp/x", "competence": "devis"})
    assert res.status_code == 401


def test_la_route_atteint_reellement_le_registre(client, entetes, monkeypatch):
    appels = []

    def double(nom, capacite, compte=None, **parametres):
        appels.append((nom, capacite, parametres))
        return a_confirmer(action="evoluer", cible="hermes_evolution",
                           message="Pret : ...", risque="HIGH", en_attente="abc123")

    monkeypatch.setattr(hermes_evolution.registre, "executer", double)

    res = client.post(
        "/api/hermes-evolution/evoluer",
        json={"depot_cible": "/tmp/hermes-agent", "competence": "github-code-review"},
        headers=entetes)

    assert res.status_code == 200
    assert res.json()["status"] == "NEEDS_CONFIRMATION"
    assert appels[0] == ("hermes_evolution", "evoluer", {
        "depot_cible": "/tmp/hermes-agent", "competence": "github-code-review",
        "iterations": 3, "source_evaluation": "synthetic"})


def test_un_refus_reste_un_200_avec_le_statut_dans_le_corps(client, entetes, monkeypatch):
    """Meme regle que `/api/actions/*confirm*` : le code HTTP dit que la
    requete a ete traitee, le corps dit le sort de l'action."""
    def double(nom, capacite, compte=None, **parametres):
        return echec(action="evoluer", cible="hermes_evolution", message="Refuse : ...")

    monkeypatch.setattr(hermes_evolution.registre, "executer", double)

    res = client.post(
        "/api/hermes-evolution/evoluer",
        json={"depot_cible": "/tmp/x", "competence": "devis"}, headers=entetes)

    assert res.status_code == 200
    assert res.json()["status"] == "FAILED"


def test_timeout_secondes_optionnel_n_est_transmis_que_si_fourni(client, entetes, monkeypatch):
    appels = []

    def double(nom, capacite, compte=None, **parametres):
        appels.append(parametres)
        return succes(action="evoluer", cible="hermes_evolution", message="ok", preuve="x@y")

    monkeypatch.setattr(hermes_evolution.registre, "executer", double)

    client.post(
        "/api/hermes-evolution/evoluer",
        json={"depot_cible": "/tmp/x", "competence": "devis", "timeout_secondes": 600},
        headers=entetes)

    assert appels[0]["timeout_secondes"] == 600

    client.post(
        "/api/hermes-evolution/evoluer",
        json={"depot_cible": "/tmp/x", "competence": "devis"}, headers=entetes)

    assert "timeout_secondes" not in appels[1]
