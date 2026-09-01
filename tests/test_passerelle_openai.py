"""La passerelle compatible OpenAI répond toujours quelque chose.

Mesuré le 01/09/2026 : avec Ollama éteint, `/v1/chat/completions` rendait
`500 Internal Server Error`, `text/plain`, corps vide. C'est la surface que
les outils **extérieurs** utilisent : le client ne pouvait pas distinguer
« le service est tombé » de « ta requête est invalide ». `/api/chat` disait
déjà « Ollama hors-ligne » proprement ; cette passerelle non.

Et son flux mourait en silence, exactement comme `/api/chat/stream` avant
sa correction du même jour.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite

CLE = "cle-de-test-passerelle"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE}"}


@pytest.fixture
def fournisseur_en_panne(monkeypatch):
    import apps.backend.routers.chat as chat
    import apps.backend.routers.openai_gateway as passerelle

    async def tombe(*_a, **_k):
        raise RuntimeError("Ollama ne repond pas")
        yield  # pragma: no cover - rend la fonction asynchrone génératrice

    async def tombe_aussi(*_a, **_k):
        raise RuntimeError("Ollama ne repond pas")

    async def conversation(*_a, **_k):
        return "CHAT"

    monkeypatch.setattr(passerelle.fast_provider, "generate_stream", tombe)
    monkeypatch.setattr(chat.fast_provider, "generate", tombe_aussi)
    monkeypatch.setattr(passerelle.orchestrator, "analyze_intent", conversation)


class TestUnePanneNeSortPasEn500Nu:
    def test_le_client_recoit_un_objet_erreur_json(
        self, client, entetes, fournisseur_en_panne
    ):
        reponse = client.post(
            "/v1/chat/completions", headers=entetes,
            json={"model": "usman-chat", "messages": [{"role": "user", "content": "salut"}]})

        assert reponse.status_code == 503, "une panne de service n'est pas un 500"
        assert reponse.headers["content-type"].startswith("application/json")
        erreur = reponse.json()["error"]
        assert erreur["type"] == "service_unavailable"
        assert "Ollama ne repond pas" in erreur["message"]

    def test_le_flux_dit_la_panne_et_se_ferme(
        self, client, entetes, fournisseur_en_panne
    ):
        with client.stream(
            "POST", "/v1/chat/completions", headers=entetes,
            json={"model": "usman-chat", "stream": True,
                  "messages": [{"role": "user", "content": "salut"}]},
        ) as reponse:
            lignes = [ligne for ligne in reponse.iter_lines() if ligne]

        assert lignes, "flux vide : la panne est invisible pour le client"
        assert lignes[-1].strip() == "data: [DONE]", (
            "sans [DONE], le client attend indéfiniment"
        )
        assert any("Ollama ne repond pas" in ligne for ligne in lignes)


class TestUnRefusResteUnRefus:
    """Une panne de service ne doit pas maquiller un problème d'accès."""

    def test_sans_cle_c_est_401_pas_503(self, client):
        reponse = client.post(
            "/v1/chat/completions",
            json={"model": "usman-chat", "messages": [{"role": "user", "content": "x"}]})
        assert reponse.status_code == 401

    def test_une_mauvaise_cle_reste_401(self, client, fournisseur_en_panne):
        reponse = client.post(
            "/v1/chat/completions", headers={"Authorization": "Bearer faux"},
            json={"model": "usman-chat", "messages": [{"role": "user", "content": "x"}]})
        assert reponse.status_code == 401, "un refus d'accès s'est fait passer pour une panne"


class TestLeCheminNormalNeChangePas:
    def test_les_modeles_restent_annonces(self, client, entetes):
        donnees = client.get("/v1/models", headers=entetes).json()
        identifiants = {m["id"] for m in donnees["data"]}
        assert "usman-chat" in identifiants
        assert donnees["object"] == "list"
