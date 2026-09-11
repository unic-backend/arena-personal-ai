"""`/api/image` — mission ARENA x HIDREAM-I1 (DEC-0085).

Meme discipline que `tests/test_video_production_router.py` : la route
atteint reellement `video_production_agent`/le registre (monkeypatche les
fonctions, jamais un double independant qui rejouerait sa propre logique).
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import image_generation

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def test_generer_exige_la_cle(client):
    res = client.post("/api/image/generer", json={"prompt": "un chat"})
    assert res.status_code == 401


def test_generer_atteint_reellement_l_agent(client, entetes, monkeypatch):
    appels = []

    async def double(prompt, **kwargs):
        appels.append((prompt, kwargs))
        return {"statut": "NEEDS_CONFIRMATION", "message": "en attente"}

    monkeypatch.setattr(image_generation.video_production_agent, "generer_image", double)

    res = client.post("/api/image/generer",
                      json={"prompt": "un phare au clair de lune", "width": 1024, "seed": 3},
                      headers=entetes)

    assert res.status_code == 200
    assert appels[0][0] == "un phare au clair de lune"
    assert appels[0][1]["width"] == 1024
    assert appels[0][1]["seed"] == 3


def test_une_exception_de_l_agent_devient_une_erreur_500_pas_un_crash_muet(
    client, entetes, monkeypatch,
):
    async def casse(prompt, **kwargs):
        raise RuntimeError("worker indisponible")

    monkeypatch.setattr(image_generation.video_production_agent, "generer_image", casse)

    res = client.post("/api/image/generer", json={"prompt": "un chat"}, headers=entetes)

    assert res.status_code == 500
    assert "worker indisponible" in res.json()["detail"]


def test_capacites_lit_reellement_le_registre(client, entetes, monkeypatch):
    class FauxResultat:
        def to_dict(self):
            return {"status": "SUCCESS", "response": "ok",
                    "detail": {"donnees": {"materiel": {"gpu": None}}}}

    appels = []
    monkeypatch.setattr(
        image_generation.registre, "executer",
        lambda nom, capacite, **kw: (appels.append((nom, capacite)), FauxResultat())[1])

    res = client.get("/api/image/capacites", headers=entetes)

    assert res.status_code == 200
    assert appels == [("hidream", "capacites")]


def test_etat_lit_reellement_le_registre_avec_le_bon_job_id(client, entetes, monkeypatch):
    class FauxResultat:
        def to_dict(self):
            return {"status": "SUCCESS", "response": "ok"}

    appels = []
    monkeypatch.setattr(
        image_generation.registre, "executer",
        lambda nom, capacite, **kw: (appels.append((nom, capacite, kw)), FauxResultat())[1])

    res = client.get("/api/image/j1", headers=entetes)

    assert res.status_code == 200
    assert appels == [("hidream", "etat_travail", {"job_id": "j1"})]


# --- ComfyUI (mission ARENA x COMFYUI, DEC-0087) — additif, defaut inchange ---

def test_generer_transmet_backend_et_workflow_id(client, entetes, monkeypatch):
    appels = []

    async def double(prompt, **kwargs):
        appels.append((prompt, kwargs))
        return {"statut": "NEEDS_CONFIRMATION", "message": "en attente"}

    monkeypatch.setattr(image_generation.video_production_agent, "generer_image", double)

    res = client.post(
        "/api/image/generer",
        json={"prompt": "un chat", "backend": "comfyui", "workflow_id": "text_to_image",
              "ckpt_name": "v1-5.safetensors"},
        headers=entetes)

    assert res.status_code == 200
    assert appels[0][1]["backend"] == "comfyui"
    assert appels[0][1]["workflow_id"] == "text_to_image"
    assert appels[0][1]["ckpt_name"] == "v1-5.safetensors"


def test_capacites_lit_le_backend_demande(client, entetes, monkeypatch):
    class FauxResultat:
        def to_dict(self):
            return {"status": "SUCCESS", "response": "ok"}

    appels = []
    monkeypatch.setattr(
        image_generation.registre, "executer",
        lambda nom, capacite, **kw: (appels.append((nom, capacite)), FauxResultat())[1])

    res = client.get("/api/image/capacites?backend=comfyui", headers=entetes)

    assert res.status_code == 200
    assert appels == [("comfyui", "capacites")]


def test_etat_lit_le_backend_demande(client, entetes, monkeypatch):
    class FauxResultat:
        def to_dict(self):
            return {"status": "SUCCESS", "response": "ok"}

    appels = []
    monkeypatch.setattr(
        image_generation.registre, "executer",
        lambda nom, capacite, **kw: (appels.append((nom, capacite, kw)), FauxResultat())[1])

    res = client.get("/api/image/p1?backend=comfyui", headers=entetes)

    assert res.status_code == 200
    assert appels == [("comfyui", "etat_travail", {"job_id": "p1"})]


def test_workflows_rend_le_catalogue_sans_toucher_au_registre(client, entetes, monkeypatch):
    appels = []
    monkeypatch.setattr(
        image_generation.registre, "executer",
        lambda *a, **kw: appels.append((a, kw)) or (_ for _ in ()).throw(AssertionError(
            "le catalogue ne doit jamais atteindre le registre/connecteur")))

    res = client.get("/api/image/workflows", headers=entetes)

    assert res.status_code == 200
    identifiants = {w["identifiant"] for w in res.json()["workflows"]}
    assert "text_to_image" in identifiants
    assert appels == []


def test_workflows_exige_la_cle(client):
    res = client.get("/api/image/workflows")
    assert res.status_code == 401
