"""`/api/video/projet` — le point d'entree reel de `VideoProductionAgent`.

Avant ce routeur, l'agent existait, testait vert contre des doubles, mais
n'etait atteint par AUCUN point d'entree (`docs/CURRENT_TASK.md`,
DEC-0037). Ces tests verifient que la route atteint reellement l'agent
(monkeypatche `video_production_agent.run`, pas un double independant) et
que le controle de chemin (MEDIA_DIR) tient — meme discipline que
`/api/process-video`.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.config import MEDIA_DIR
from apps.backend.routers import video_production

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def test_la_route_exige_la_cle(client):
    assert client.post("/api/video/projet", json={"objectif": "x"}).status_code == 401


def test_la_route_atteint_reellement_l_agent(client, entetes, monkeypatch):
    appels = []

    async def double(objectif, context=None):
        appels.append((objectif, context))
        return {"status": "success", "agent": "VideoProductionAgent",
                "response": "ok", "projet": {}}

    monkeypatch.setattr(video_production.video_production_agent, "run", double)

    res = client.post("/api/video/projet",
                      json={"objectif": "fais une video promo"}, headers=entetes)

    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert appels[0][0] == "fais une video promo"


def test_les_references_sont_transmises_au_contexte(client, entetes, monkeypatch, tmp_path):
    appels = []

    async def double(objectif, context=None):
        appels.append(context)
        return {"status": "success", "response": "ok"}

    monkeypatch.setattr(video_production.video_production_agent, "run", double)
    fichier = MEDIA_DIR / "incoming" / "test_video_projet.jpg"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(b"donnees")
    try:
        res = client.post(
            "/api/video/projet",
            json={"objectif": "analyse", "references": [str(fichier)]},
            headers=entetes)

        assert res.status_code == 200
        assert appels[0]["references"] == [str(fichier.resolve())]
    finally:
        fichier.unlink(missing_ok=True)


def test_une_reference_hors_media_dir_est_refusee(client, entetes, monkeypatch):
    async def double(objectif, context=None):
        raise AssertionError("l'agent n'aurait jamais du etre appele")

    monkeypatch.setattr(video_production.video_production_agent, "run", double)

    res = client.post(
        "/api/video/projet",
        json={"objectif": "x", "references": ["/etc/passwd"]},
        headers=entetes)

    assert res.status_code == 403


def test_le_mode_team_transmet_les_capacites_choisies(client, entetes, monkeypatch):
    appels = []

    async def double(objectif, context=None):
        appels.append(context)
        return {"status": "success", "response": "ok"}

    monkeypatch.setattr(video_production.video_production_agent, "run", double)

    client.post("/api/video/projet",
               json={"objectif": "x", "capacites": ["vision", "montage"]},
               headers=entetes)

    assert appels[0]["capacites"] == ["vision", "montage"]


def test_sans_capacites_le_contexte_ne_les_mentionne_pas(client, entetes, monkeypatch):
    """Mode AUTO par defaut : ne force pas une cle absente dans le contexte."""
    appels = []

    async def double(objectif, context=None):
        appels.append(context)
        return {"status": "success", "response": "ok"}

    monkeypatch.setattr(video_production.video_production_agent, "run", double)

    client.post("/api/video/projet", json={"objectif": "x"}, headers=entetes)

    assert "capacites" not in appels[0]


def test_personnage_id_est_transmis_au_contexte(client, entetes, monkeypatch):
    """Mission ARENA x AGENT HEROES (DEC-0084) : la route transmet
    `personnage_id`, elle ne resout jamais le personnage elle-meme — c'est
    `VideoProductionAgent.run` qui le fait (meme separation route/logique
    que le reste de ce fichier)."""
    appels = []

    async def double(objectif, context=None):
        appels.append(context)
        return {"status": "success", "response": "ok"}

    monkeypatch.setattr(video_production.video_production_agent, "run", double)

    client.post("/api/video/projet",
               json={"objectif": "x", "personnage_id": "aissatou-abc123"},
               headers=entetes)

    assert appels[0]["personnage_id"] == "aissatou-abc123"


def test_sans_personnage_id_le_contexte_ne_le_mentionne_pas(client, entetes, monkeypatch):
    appels = []

    async def double(objectif, context=None):
        appels.append(context)
        return {"status": "success", "response": "ok"}

    monkeypatch.setattr(video_production.video_production_agent, "run", double)

    client.post("/api/video/projet", json={"objectif": "x"}, headers=entetes)

    assert "personnage_id" not in appels[0]


def test_une_exception_de_l_agent_devient_une_erreur_500_pas_un_crash_muet(
    client, entetes, monkeypatch,
):
    async def casse(objectif, context=None):
        raise RuntimeError("modele indisponible")

    monkeypatch.setattr(video_production.video_production_agent, "run", casse)

    res = client.post("/api/video/projet", json={"objectif": "x"}, headers=entetes)

    assert res.status_code == 500
    assert "modele indisponible" in res.json()["detail"]
