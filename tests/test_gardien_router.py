"""`/api/gardien/rapport` et `/api/gardien/cycle` : le branchement HTTP.

Le cycle réel (ruff/pytest/orphelins) est mesuré à la main pendant l'écriture
(voir DEC-0014) — ici, un `Gardien` de test est injecté pour rester rapide et
déterministe.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import gardien as routeur_gardien
from core.guardian.diagnostics import Constat
from core.guardian.file_maintenance import FileDeMaintenance
from core.guardian.gardien import Gardien

CLE = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE}"}

UN_BUG = Constat(categorie="BUG", gravite="P2", description="test en echec : x",
                 fichier="tests/test_x.py")


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def file_de_test(tmp_path, monkeypatch):
    fm = FileDeMaintenance(db_path=str(tmp_path / "maintenance.db"))
    monkeypatch.setattr(routeur_gardien, "file_maintenance", fm)
    return fm


@pytest.fixture
def gardien_de_test(file_de_test, monkeypatch):
    def diagnostiquer_fixe(executer):
        return [UN_BUG]
    import core.guardian.gardien as module_gardien
    monkeypatch.setattr(module_gardien, "diagnostiquer_tout", diagnostiquer_fixe)
    g = Gardien(file_maintenance=file_de_test)
    monkeypatch.setattr(routeur_gardien, "gardien", g)
    return g


class TestAuthentification:
    def test_le_rapport_exige_la_cle(self, client):
        reponse = client.get("/api/gardien/rapport")  # sans en-tete Authorization

        assert reponse.status_code == 401

    def test_le_cycle_exige_la_cle(self, client):
        reponse = client.post("/api/gardien/cycle")  # sans en-tete Authorization

        assert reponse.status_code == 401


class TestRapport:
    def test_sans_tache_le_rapport_est_vide(self, client, file_de_test):
        reponse = client.get("/api/gardien/rapport", headers=ENTETES)

        assert reponse.status_code == 200
        corps = reponse.json()
        assert corps["total_ouvertes"] == 0
        assert corps["taches_ouvertes"] == []

    def test_le_rapport_reflete_la_file_sans_lancer_de_cycle(self, client, file_de_test):
        file_de_test.enregistrer_constats([UN_BUG])

        reponse = client.get("/api/gardien/rapport", headers=ENTETES)

        assert reponse.json()["total_ouvertes"] == 1


class TestCycle:
    def test_un_cycle_peuple_la_file_et_la_rend(self, client, gardien_de_test, file_de_test):
        reponse = client.post("/api/gardien/cycle", headers=ENTETES)

        assert reponse.status_code == 200
        corps = reponse.json()
        assert corps["nouvelles"] == 1
        assert corps["total_ouvertes"] == 1
        assert len(file_de_test.ouvertes()) == 1

    def test_un_second_cycle_ne_recree_pas_la_meme_tache(self, client, gardien_de_test):
        client.post("/api/gardien/cycle", headers=ENTETES)
        reponse = client.post("/api/gardien/cycle", headers=ENTETES)

        corps = reponse.json()
        assert corps["nouvelles"] == 0
        assert corps["revues"] == 1
