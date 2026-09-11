"""`/api/memory` — mission ARENA x AI MEMORY VAULT (DEC-0090).

Meme discipline que `tests/test_executive_router.py` : la route atteint
reellement `MemoirePersonnelle`, jamais un double qui rejouerait sa propre
logique. `memoire_personnelle` est remplace par une instance isolee (fichier
temporaire) pour que ces tests ne touchent jamais `data/database/memory.db`.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import memory as routeur_memoire
from core.memory.personnelle import MemoirePersonnelle

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    monkeypatch.setattr(
        routeur_memoire, "memoire_personnelle",
        MemoirePersonnelle(db_path=str(tmp_path / "memoire.db")),
    )
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


class TestAuthentification:
    @pytest.mark.parametrize("methode,chemin", [
        ("GET", "/api/memory"),
        ("GET", "/api/memory/search?q=x"),
        ("POST", "/api/memory"),
        ("DELETE", "/api/memory/x"),
    ])
    def test_toute_route_exige_la_cle(self, client, methode, chemin):
        res = client.request(methode, chemin, json={} if methode == "POST" else None)
        assert res.status_code == 401


class TestCreationEtGouvernance:
    def test_creer_rend_toujours_une_inference(self, client, entetes):
        res = client.post("/api/memory", headers=entetes,
                           json={"contenu": "x", "type": "semantic", "source": "test"})
        assert res.status_code == 200
        assert res.json()["nature"] == "INFERENCE"

    def test_creer_avec_un_type_inconnu_rend_422(self, client, entetes):
        res = client.post("/api/memory", headers=entetes,
                           json={"contenu": "x", "type": "pas-un-type", "source": "test"})
        assert res.status_code == 422

    def test_creer_un_contenu_secret_est_refuse(self, client, entetes):
        # Construit par concatenation, jamais en litteral (voir la meme note
        # dans tests/core/test_memoire_gouvernance.py::TestSecretsRefuses).
        cle_factice = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
        res = client.post("/api/memory", headers=entetes, json={
            "contenu": f"ma cle est {cle_factice}",
            "type": "semantic", "source": "test",
        })
        assert res.status_code == 422

    def test_approve_promeut_en_fait(self, client, entetes):
        cree = client.post("/api/memory", headers=entetes,
                            json={"contenu": "x", "type": "semantic", "source": "test"}).json()
        res = client.post(f"/api/memory/{cree['id']}/approve", headers=entetes,
                           json={"source": "proprietaire"})
        assert res.status_code == 200
        assert res.json()["nature"] == "FACT"

    def test_approve_id_inconnu_rend_404(self, client, entetes):
        res = client.post("/api/memory/inconnu/approve", headers=entetes, json={"source": "x"})
        assert res.status_code == 404

    def test_reject_exclut_de_la_liste_normale(self, client, entetes):
        cree = client.post("/api/memory", headers=entetes,
                            json={"contenu": "faux", "type": "semantic", "source": "test"}).json()
        client.post(f"/api/memory/{cree['id']}/reject", headers=entetes,
                    json={"source": "correction"})
        res = client.get("/api/memory", headers=entetes)
        assert not any(s["id"] == cree["id"] for s in res.json())
        res_inclus = client.get("/api/memory?inclure_rejetes=true", headers=entetes)
        assert any(s["id"] == cree["id"] for s in res_inclus.json())

    def test_archive_puis_reactivate(self, client, entetes):
        cree = client.post("/api/memory", headers=entetes,
                            json={"contenu": "x", "type": "semantic", "source": "test"}).json()
        client.post(f"/api/memory/{cree['id']}/archive", headers=entetes, json={"source": "termine"})
        assert not any(
            s["id"] == cree["id"]
            for s in client.get("/api/memory", headers=entetes).json()
        )
        client.post(f"/api/memory/{cree['id']}/reactivate", headers=entetes, json={"source": "reouvert"})
        assert any(
            s["id"] == cree["id"]
            for s in client.get("/api/memory", headers=entetes).json()
        )

    def test_delete_supprime_reellement(self, client, entetes):
        cree = client.post("/api/memory", headers=entetes,
                            json={"contenu": "x", "type": "semantic", "source": "test"}).json()
        res = client.delete(f"/api/memory/{cree['id']}", headers=entetes)
        assert res.status_code == 200
        assert client.get(f"/api/memory/{cree['id']}", headers=entetes).status_code == 404

    def test_delete_id_inconnu_rend_404(self, client, entetes):
        res = client.delete("/api/memory/inconnu", headers=entetes)
        assert res.status_code == 404


class TestRecherche:
    def test_search_rend_ce_qui_est_pertinent(self, client, entetes):
        client.post("/api/memory", headers=entetes,
                     json={"contenu": "Le tarif pose BA13 est 5000 F/m2.", "type": "semantic", "source": "test"})
        res = client.get("/api/memory/search", headers=entetes, params={"q": "tarif BA13"})
        assert res.status_code == 200
        assert any("tarif" in s["contenu"].lower() for s in res.json())


class TestExport:
    def test_export_inclut_les_rejetes_et_dit_qu_il_n_est_pas_chiffre(self, client, entetes):
        cree = client.post("/api/memory", headers=entetes,
                            json={"contenu": "x", "type": "semantic", "source": "test"}).json()
        client.post(f"/api/memory/{cree['id']}/reject", headers=entetes, json={"source": "correction"})
        res = client.get("/api/memory/export/all", headers=entetes)
        assert res.status_code == 200
        corps = res.json()
        assert corps["export_chiffre"] is False
        assert any(s["id"] == cree["id"] for s in corps["souvenirs"])


class TestImport:
    def test_import_txt_cree_des_candidats(self, client, entetes):
        fichier = ("notes.txt", b"I am building GalSenIA using FastAPI.", "text/plain")
        res = client.post("/api/memory/import", headers=entetes, files={"fichier": fichier})
        assert res.status_code == 200
        corps = res.json()
        assert corps["format_detecte"] == "txt"
        assert len(corps["crees"]) >= 1
        assert all(s["nature"] == "INFERENCE" for s in corps["crees"])

    def test_import_format_inconnu_rend_400(self, client, entetes):
        fichier = ("fichier.exe", b"binaire", "application/octet-stream")
        res = client.post("/api/memory/import", headers=entetes, files={"fichier": fichier})
        assert res.status_code == 400
