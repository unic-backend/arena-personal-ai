"""`/api/memory` — mission ARENA x AI MEMORY VAULT (DEC-0090).

Meme discipline que `tests/test_executive_router.py` : la route atteint
reellement `MemoirePersonnelle`, jamais un double qui rejouerait sa propre
logique. `memoire_personnelle` est remplace par une instance isolee (fichier
temporaire) pour que ces tests ne touchent jamais `data/database/memory.db`.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import memory as routeur_memoire
from core.memory.personnelle import MemoirePersonnelle

CLE_DE_TEST = "cle-de-test"

#: La racine du depot, pour lancer `apps/backend/runtime.py` dans un
#: sous-processus sans dependre du repertoire courant de pytest.
RACINE = Path(__file__).resolve().parents[1]


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


class TestLeCoffreEstJoignableDepuisLeBackend:
    """DEC-0097 : `/api/memory` acceptait `sensible: true` dans son schema et
    le refusait TOUJOURS en 422, parce que `apps/backend/runtime.py` construisait
    `MemoirePersonnelle` SANS coffre. Le chiffrement au repos (DEC-0090) n'etait
    joignable que par le serveur MCP — jamais depuis son telephone.

    Le refus etait honnete (jamais un faux succes, jamais un souvenir ecrit en
    clair sous couvert de securite) : c'est la capacite qui manquait, pas la
    garantie.
    """

    def test_sans_phrase_de_passe_la_route_refuse_toujours_proprement(
        self, monkeypatch, tmp_path, entetes,
    ):
        """Sans la variable d'environnement, rien ne change : 422, jamais un
        souvenir sensible ecrit en clair."""
        monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
        monkeypatch.setattr(
            routeur_memoire, "memoire_personnelle",
            MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"), coffre=None),
        )
        client = TestClient(main.app, raise_server_exceptions=False)

        res = client.post("/api/memory", headers=entetes, json={
            "contenu": "Le code du portail est 4821.", "type": "semantic",
            "source": "le proprietaire", "sensible": True,
        })

        assert res.status_code == 422
        assert "coffre" in res.json()["detail"].lower()

    def test_avec_une_phrase_de_passe_le_souvenir_sensible_est_ecrit_chiffre(
        self, monkeypatch, tmp_path, entetes,
    ):
        import sqlite3

        from core.memory.chiffrement import Coffre

        monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
        base = tmp_path / "memoire.db"
        monkeypatch.setattr(
            routeur_memoire, "memoire_personnelle",
            MemoirePersonnelle(
                db_path=str(base),
                coffre=Coffre("phrase-de-test-longue", chemin_sel=tmp_path / "vault_salt"),
            ),
        )
        client = TestClient(main.app, raise_server_exceptions=False)

        res = client.post("/api/memory", headers=entetes, json={
            "contenu": "Le code du portail est 4821.", "type": "semantic",
            "source": "le proprietaire", "sensible": True,
        })

        assert res.status_code == 200, res.text
        assert res.json()["sensible"] is True
        # Sur le DISQUE, ce doit etre du chiffre — la garantie de DEC-0090.
        with sqlite3.connect(base) as connexion:
            stocke = connexion.execute(
                "SELECT contenu FROM souvenirs WHERE identifiant = ?",
                (res.json()["id"],),
            ).fetchone()[0]
        assert "4821" not in stocke, "le souvenir sensible est en clair sur le disque"
        # Et relu par la route, il redevient lisible.
        relu = client.get(f"/api/memory/{res.json()['id']}", headers=entetes)
        assert "4821" in relu.json()["contenu"]

    @pytest.mark.parametrize("phrase,coffre_attendu,sel_attendu", [
        (None, "NoneType", False),
        ("phrase-de-test-longue", "Coffre", True),
    ])
    def test_le_runtime_branche_le_coffre_sur_l_environnement(
        self, tmp_path, phrase, coffre_attendu, sel_attendu,
    ):
        """La ligne qui manquait, verifiee sur le VRAI `apps/backend/runtime.py`.

        Dans un sous-processus, parce que ce module construit la plateforme a
        l'import : le recharger dans celui-ci remplacerait les objets que les
        autres tests utilisent. Sans variable -> aucun coffre, exactement le
        comportement d'avant ; avec variable -> un coffre, et le sel conserve
        a cote de la base.
        """
        import json
        import os
        import subprocess
        import sys

        from core.memory.chiffrement import NOM_FICHIER_SEL, VARIABLE_PASSPHRASE

        base = tmp_path / "database" / "memory.db"
        base.parent.mkdir(parents=True)
        environnement = {
            **os.environ,
            "USMAN_DB_PATH": str(base),
            "PYTHONPATH": str(RACINE),
        }
        if phrase is None:
            environnement.pop(VARIABLE_PASSPHRASE, None)
        else:
            environnement[VARIABLE_PASSPHRASE] = phrase

        programme = (
            "import json\n"
            "from apps.backend.runtime import memoire_personnelle\n"
            "coffre = memoire_personnelle.coffre\n"
            "print(json.dumps({'coffre': type(coffre).__name__}))\n"
        )
        acheve = subprocess.run(
            [sys.executable, "-c", programme], capture_output=True, text=True,
            env=environnement, cwd=str(RACINE), timeout=300,
        )

        assert acheve.returncode == 0, acheve.stderr[-2000:]
        mesure = json.loads(acheve.stdout.strip().splitlines()[-1])
        assert mesure["coffre"] == coffre_attendu
        assert (base.parent / NOM_FICHIER_SEL).exists() is False, (
            "le sel ne doit etre ecrit qu'a la premiere ECRITURE sensible, "
            "jamais au seul demarrage")
        assert sel_attendu == (mesure["coffre"] == "Coffre")
