"""Surface HTTP d'Usman : ce qui est ouvert, ce qui est fermé.

Ces tests tournent hors ligne : ils mesurent l'authentification et le CORS, pas
les réponses du modèle. Le test qui a besoin d'Ollama porte le marqueur
`integration`.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite

CLE_DE_TEST = "cle-de-test"
ROUTES_METIER = ["/api/upload", "/api/process-video", "/api/chat", "/api/chat/stream"]


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """Client HTTP avec une clé API connue ; les erreurs applicatives deviennent des 500."""
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def test_health_repond_et_annonce_l_etat_d_ollama(client):
    res = client.get("/health")

    assert res.status_code == 200
    corps = res.json()
    # « healthy » ou « degraded » selon qu'Ollama tourne : les deux sont des
    # réponses justes. Exiger « healthy » ferait échouer le test sur une machine
    # sans Ollama, ce qui ne dit rien sur l'API.
    assert corps["status"] in {"healthy", "degraded"}
    assert corps["ollama_available"] is (corps["status"] == "healthy")
    assert len(corps["agents_active"]) > 0


@pytest.mark.parametrize("route", ROUTES_METIER)
def test_les_routes_metier_exigent_la_cle(client, route):
    assert client.post(route, json={"prompt": "x"}).status_code == 401


@pytest.mark.parametrize("route", ROUTES_METIER)
def test_une_mauvaise_cle_est_refusee(client, route):
    res = client.post(route, json={"prompt": "x"}, headers={"Authorization": "Bearer faux"})

    assert res.status_code == 401


@pytest.mark.parametrize("route", ROUTES_METIER)
def test_avec_la_bonne_cle_l_authentification_n_est_plus_la_cause_du_refus(
    client, entetes, route
):
    assert client.post(route, json={"prompt": "x"}, headers=entetes).status_code != 401


def test_la_passerelle_v1_exige_la_cle(client, entetes):
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers=entetes).status_code == 200


def test_sans_cle_configuree_la_passerelle_est_desactivee(monkeypatch, entetes):
    """Une clé vide ne doit pas ouvrir l'accès : elle doit le fermer."""
    monkeypatch.setattr(securite, "USMAN_API_KEY", "")
    client_sans_cle = TestClient(main.app, raise_server_exceptions=False)

    assert client_sans_cle.get("/v1/models", headers=entetes).status_code == 500


def test_une_origine_inconnue_est_refusee_par_le_cors(client):
    res = client.options(
        "/api/chat",
        headers={
            "Origin": "https://site-inconnu.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert res.headers.get("access-control-allow-origin") is None


def test_les_interfaces_locales_sont_autorisees_par_le_cors(client):
    for origine in main.ALLOWED_ORIGINS:
        res = client.options(
            "/api/chat",
            headers={
                "Origin": origine,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

        assert res.headers.get("access-control-allow-origin") == origine


def test_l_etoile_n_est_jamais_une_origine_autorisee():
    assert "*" not in main.ALLOWED_ORIGINS


@pytest.mark.integration
def test_le_chat_repond_reellement(client, entetes, ollama_en_ligne):
    res = client.post(
        "/api/chat",
        json={"prompt": "Confirme que l'API Usman est fonctionnelle en une phrase courte."},
        headers=entetes,
    )

    assert res.status_code == 200
    assert res.json()["status"] == "success"
