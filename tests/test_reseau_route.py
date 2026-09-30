"""`/api/reseau/sante` : le branchement HTTP de la sante reseau (DEC-0202).

L'adaptateur est injecte pour rester deterministe : la route ne doit ni lancer
de test de debit, ni toucher un vrai reseau. Elle protege l'acces par la meme
cle que `/api/observability` et `/api/gardien/rapport`.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import reseau as routeur_reseau
from core.reseau.sante_reseau import SanteReseau, StatutReseau

CLE = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE}"}


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False)


def test_la_sante_exige_la_cle(client):
    reponse = client.get("/api/reseau/sante")  # sans en-tete Authorization
    assert reponse.status_code == 401


def test_la_sante_rend_le_schema(client, monkeypatch):
    fixe = SanteReseau(
        statut=StatutReseau.OPERATIONNEL, source="natif",
        mesures={"network_status": "up", "latency": 8.0, "download": None},
        message="ok", erreur=None)
    monkeypatch.setattr(routeur_reseau, "evaluer_sante_reseau", lambda registre: fixe)

    reponse = client.get("/api/reseau/sante", headers=ENTETES)
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["status"] == "SUCCESS"
    assert corps["source"] == "natif"
    assert corps["mesures"]["download"] is None  # jamais fabrique


def test_la_route_utilise_le_registre_partage(client, monkeypatch):
    """La route passe le registre du runtime a l'adaptateur, pas un autre."""
    from apps.backend.runtime import registre as registre_runtime

    vus = {}

    def espion(registre):
        vus["registre"] = registre
        return SanteReseau(statut=StatutReseau.INCONNU, source="aucun")

    monkeypatch.setattr(routeur_reseau, "evaluer_sante_reseau", espion)
    client.get("/api/reseau/sante", headers=ENTETES)
    assert vus["registre"] is registre_runtime
