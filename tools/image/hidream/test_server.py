"""Tests du worker HiDream — a lancer dans SON environnement isole ou, pour
la couche HTTP/gestion de taches ci-dessous, directement ici : cette moitie
du serveur n'importe torch/diffusers/transformers qu'A L'INTERIEUR de
`_charger_pipeline`/`_generer_en_fond`, jamais au niveau du module — un
choix deliberement different de `tools/audio/csm_service/server.py` (qui
importe `torch` en tete de fichier) pour que CETTE couche reste testable
sans les 60 Go de poids qu'elle orchestre.

`pyproject.toml` (`testpaths = ["tests"]`) ne scanne pas ce dossier : ce
fichier est invisible a la suite principale d'ARENA, volontairement.

    cd tools/image/hidream
    pip install fastapi httpx pytest
    pytest test_server.py -q
"""
import threading
import time
from pathlib import Path

import pytest
import serveur_hidream as server
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def etat_propre():
    server._ETAT.update({
        "pipe": None, "variante_chargee": None, "device": None,
        "erreur_chargement": None, "dernier_usage": None,
    })
    server._TACHES.clear()
    yield
    server._ETAT.update({
        "pipe": None, "variante_chargee": None, "device": None,
        "erreur_chargement": None, "dernier_usage": None,
    })
    server._TACHES.clear()


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def torch_minimal(monkeypatch):
    """Un `torch` minimal, injecte dans `sys.modules`, pour les tests qui
    exercent `_generer_en_fond` sans l'environnement isole reel (qui, lui,
    a le vrai torch). Couvre exactement la surface que ce fichier appelle —
    `Generator`/`manual_seed`, `randint`, `inference_mode`, `cuda` — jamais
    plus. Un `import torch` reel, dans le worker deploye, l'emporte : ce
    module n'existe que le temps du test (`sys.modules` restaure par
    `monkeypatch` a la fin)."""
    import contextlib
    import sys
    import types

    faux_torch = types.ModuleType("torch")

    class _Generator:
        def __init__(self, _device):
            pass

        def manual_seed(self, seed):
            return self

    def _randint(_low, _high, _size):
        class _T:
            def item(self_inner):
                return 0
        return _T()

    faux_torch.Generator = _Generator
    faux_torch.randint = _randint
    faux_torch.inference_mode = contextlib.nullcontext
    faux_torch.cuda = types.SimpleNamespace(
        is_available=lambda: False, empty_cache=lambda: None)

    monkeypatch.setitem(sys.modules, "torch", faux_torch)
    return faux_torch


class TestHealthNeChargeJamaisLePipeline:
    def test_repond_sans_pipeline_charge(self, client, monkeypatch):
        appele = {"fois": 0}

        def _echoue_si_appele(*_a, **_k):
            appele["fois"] += 1
            raise AssertionError("health() ne doit jamais charger le pipeline")

        monkeypatch.setattr(server, "_charger_pipeline", _echoue_si_appele)
        reponse = client.get("/health")

        assert reponse.status_code == 200
        assert reponse.json()["model_loaded"] is False
        assert appele["fois"] == 0

    def test_le_materiel_est_reellement_mesure_pas_invente(self, client):
        """Sur CETTE machine (sans carte NVIDIA), la reponse doit le dire
        honnetement — jamais un GPU invente."""
        reponse = client.get("/health").json()
        assert reponse["materiel"]["gpu"] is None
        assert reponse["materiel"]["ram"] is not None
        assert reponse["materiel"]["ram"]["totale_mo"] > 0

    def test_relaie_l_erreur_de_chargement_precedente(self, client):
        server._ETAT["erreur_chargement"] = "acces gated refuse : 401"
        reponse = client.get("/health")
        assert reponse.json()["erreur_chargement"] == "acces gated refuse : 401"


class TestGenerateRefuseAvantTouteChargeLourde:
    def test_prompt_vide_refuse(self, client):
        reponse = client.post("/generate", json={"prompt": "", "variante": "fast"})
        assert reponse.status_code == 422
        assert server._TACHES == {}

    def test_variante_inconnue_refusee(self, client):
        reponse = client.post("/generate", json={"prompt": "un chat", "variante": "ultra"})
        assert reponse.status_code == 422
        assert server._TACHES == {}


class TestCycleDeVieDeTache:
    def test_generate_rend_un_job_id_immediatement(self, client, monkeypatch):
        """Le chat ARENA ne doit jamais attendre : `/generate` rend un
        identifiant avant que la generation (simulee ici) ne termine."""
        debut_generation = threading.Event()

        def _chargement_lent(variante):
            debut_generation.wait(timeout=2)
            return None

        monkeypatch.setattr(server, "_charger_pipeline", _chargement_lent)

        avant = time.monotonic()
        reponse = client.post("/generate", json={"prompt": "un chat", "variante": "fast"})
        duree = time.monotonic() - avant
        debut_generation.set()

        assert reponse.status_code == 200
        assert reponse.json()["job_id"]
        assert duree < 1.0, "generate() a attendu le chargement au lieu de rendre la main"

    def test_tache_inconnue_rend_404(self, client):
        assert client.get("/jobs/n-existe-pas").status_code == 404
        assert client.post("/jobs/n-existe-pas/cancel").status_code == 404

    def test_annuler_une_tache_en_attente_reussit(self, client):
        tache = server.Tache(id="t1", variante="fast", prompt="x")
        server._TACHES["t1"] = tache

        reponse = client.post("/jobs/t1/cancel")

        assert reponse.status_code == 200
        assert reponse.json()["state"] == "cancelled"


class TestGenererEnFond:
    """`_generer_en_fond` directement — le coeur du cycle de vie d'une
    tache, sans passer par un vrai pipeline diffusers."""

    def test_echec_de_chargement_marque_la_tache_failed(self, monkeypatch):
        monkeypatch.setattr(server, "_charger_pipeline", lambda variante: "dependances absentes")
        tache = server.Tache(id="t2", variante="fast", prompt="x")

        server._generer_en_fond(tache, server.GenerateRequete(prompt="x", variante="fast"))

        assert tache.state == "failed"
        assert tache.error == "dependances absentes"

    def test_resolution_non_publiee_est_refusee_avant_generation(self, monkeypatch):
        monkeypatch.setattr(server, "_charger_pipeline", lambda variante: None)
        appele = {"fois": 0}
        server._ETAT["pipe"] = lambda *a, **k: appele.update(fois=appele["fois"] + 1)
        tache = server.Tache(id="t3", variante="fast", prompt="x")

        requete = server.GenerateRequete(prompt="x", variante="fast", width=999, height=999)
        server._generer_en_fond(tache, requete)

        assert tache.state == "failed"
        assert "999x999" in tache.error
        assert appele["fois"] == 0, "le pipeline n'aurait jamais du etre appele sur une resolution refusee"

    def test_generation_reussie_produit_un_fichier_reel_et_valide(
        self, monkeypatch, tmp_path, torch_minimal,
    ):
        """Un vrai fichier PNG, une vraie relecture — jamais un chemin suppose.

        `torch_minimal` fournit juste assez de `torch` (generateur/seed/
        inference_mode) pour que `_generer_en_fond` s'execute reellement —
        aucun poids, aucun calcul, seulement la surface d'API que ce
        fichier appelle."""
        from PIL import Image

        class FausseImage:
            def __init__(self):
                self.images = [Image.new("RGB", (1024, 1024), color="blue")]

        class FauxPipe:
            def __call__(self, *args, **kwargs):
                return FausseImage()

        monkeypatch.setattr(server, "_charger_pipeline", lambda variante: None)
        monkeypatch.setattr(server, "SORTIE_DIR", tmp_path)
        server._ETAT["pipe"] = FauxPipe()

        tache = server.Tache(id="t4", variante="fast", prompt="un chat")
        requete = server.GenerateRequete(prompt="un chat", variante="fast", seed=42)
        server._generer_en_fond(tache, requete)

        assert tache.state == "completed"
        assert tache.seed == 42
        assert len(tache.images) == 1
        chemin = Path(tache.images[0])
        assert chemin.is_file()
        with Image.open(chemin) as relue:
            assert relue.size == (1024, 1024)

    def test_oom_pendant_la_generation_est_capture_jamais_une_exception_qui_remonte(
        self, monkeypatch, torch_minimal,
    ):
        class PipeQuiOom:
            def __call__(self, *args, **kwargs):
                class OutOfMemoryError(RuntimeError):
                    pass
                raise OutOfMemoryError("CUDA out of memory")

        monkeypatch.setattr(server, "_charger_pipeline", lambda variante: None)
        server._ETAT["pipe"] = PipeQuiOom()

        tache = server.Tache(id="t5", variante="fast", prompt="x")
        # Ne doit JAMAIS lever : le worker doit rester utilisable apres un OOM.
        server._generer_en_fond(tache, server.GenerateRequete(prompt="x", variante="fast"))

        assert tache.state == "failed"
        assert "VRAM insuffisante" in tache.error


class TestDechargementApresInactivite:
    def test_ne_decharge_pas_si_le_delai_n_est_pas_ecoule(self, monkeypatch):
        monkeypatch.setattr(server, "DELAI_DECHARGEMENT_S", 600.0)
        server._ETAT["pipe"] = object()
        server._ETAT["dernier_usage"] = time.monotonic()

        server._decharger_si_inactif()

        assert server._ETAT["pipe"] is not None

    def test_rien_a_decharger_si_aucun_pipeline_charge(self, monkeypatch):
        monkeypatch.setattr(server, "DELAI_DECHARGEMENT_S", 0.001)
        server._ETAT["pipe"] = None
        server._ETAT["dernier_usage"] = None

        server._decharger_si_inactif()  # ne doit pas lever

        assert server._ETAT["pipe"] is None
