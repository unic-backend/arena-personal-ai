"""`/api/personnages` — mission ARENA x AGENT HEROES (DEC-0084).

Meme discipline que `tests/test_video_production_router.py` : la route
atteint reellement `video_production_agent`/le registre (monkeypatche les
fonctions, jamais un double independant qui rejouerait sa propre logique).
Le registre est redirige vers `tmp_path` : jamais le vrai `data/personnages/`.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.config import MEDIA_DIR
from apps.backend.routers import personnages
from core.characters.registry import charger_personnage as charger_reel
from core.characters.registry import charger_registre as lister_reel
from core.characters.registry import creer_personnage as creer_reel

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


@pytest.fixture(autouse=True)
def registre_isole(tmp_path, monkeypatch):
    """Toutes les routes de ce fichier ecrivent dans `tmp_path`, jamais dans
    le vrai `data/personnages/` du depot."""
    dossier = tmp_path / "personnages"
    monkeypatch.setattr(
        personnages, "creer_personnage",
        lambda *a, **k: creer_reel(*a, dossier=dossier, **k))
    monkeypatch.setattr(
        personnages, "charger_personnage",
        lambda identifiant: charger_reel(identifiant, dossier=dossier))
    monkeypatch.setattr(personnages, "charger_registre", lambda: lister_reel(dossier))
    return dossier


def test_la_creation_exige_la_cle(client):
    res = client.post("/api/personnages", json={"nom": "x", "profil_visuel": "y"})
    assert res.status_code == 401


def test_creer_puis_relire_un_personnage(client, entetes):
    res = client.post("/api/personnages", json={
        "nom": "Aissatou", "description": "Presentatrice",
        "profil_visuel": "femme senegalaise, boubou bleu"}, headers=entetes)

    assert res.status_code == 200
    corps = res.json()
    assert corps["nom"] == "Aissatou"
    identifiant = corps["identifiant"]

    relu = client.get(f"/api/personnages/{identifiant}", headers=entetes)
    assert relu.status_code == 200
    assert relu.json()["profil_visuel"] == "femme senegalaise, boubou bleu"


def test_lister_rend_les_personnages_crees(client, entetes):
    client.post("/api/personnages", json={"nom": "A", "profil_visuel": "p"}, headers=entetes)
    client.post("/api/personnages", json={"nom": "B", "profil_visuel": "p"}, headers=entetes)

    res = client.get("/api/personnages", headers=entetes)

    assert res.status_code == 200
    assert {p["nom"] for p in res.json()} == {"A", "B"}


def test_personnage_inconnu_rend_404(client, entetes):
    res = client.get("/api/personnages/n-existe-pas", headers=entetes)
    assert res.status_code == 404


def test_une_image_de_reference_hors_media_dir_est_refusee(client, entetes):
    res = client.post("/api/personnages", json={
        "nom": "X", "profil_visuel": "p", "images_reference": ["/etc/passwd"],
    }, headers=entetes)
    assert res.status_code == 403


def test_une_image_de_reference_dans_media_dir_est_acceptee(client, entetes):
    fichier = MEDIA_DIR / "incoming" / "test_personnage_visage.jpg"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(b"donnees")
    try:
        res = client.post("/api/personnages", json={
            "nom": "X", "profil_visuel": "p", "images_reference": [str(fichier)],
        }, headers=entetes)

        assert res.status_code == 200
        assert res.json()["images_reference"] == [str(fichier.resolve())]
    finally:
        fichier.unlink(missing_ok=True)


def test_generer_image_atteint_reellement_l_agent(client, entetes, monkeypatch):
    appels = []
    res_creation = client.post(
        "/api/personnages", json={"nom": "X", "profil_visuel": "p"}, headers=entetes)
    identifiant = res_creation.json()["identifiant"]

    async def double(perso_id, description_scene):
        appels.append((perso_id, description_scene))
        return {"statut": "NEEDS_CONFIRMATION", "personnage_id": perso_id}

    monkeypatch.setattr(personnages.video_production_agent, "generer_image_personnage", double)

    res = client.post(f"/api/personnages/{identifiant}/image",
                      json={"description_scene": "marche au soleil"}, headers=entetes)

    assert res.status_code == 200
    assert appels == [(identifiant, "marche au soleil")]


def test_generer_image_sur_personnage_inconnu_rend_404_sans_appeler_l_agent(
    client, entetes, monkeypatch,
):
    async def jamais(*a, **k):
        raise AssertionError("l'agent n'aurait jamais du etre appele")

    monkeypatch.setattr(personnages.video_production_agent, "generer_image_personnage", jamais)

    res = client.post("/api/personnages/n-existe-pas/image",
                      json={"description_scene": "x"}, headers=entetes)

    assert res.status_code == 404


def test_appliquer_identite_verifie_le_chemin_media_dir(client, entetes):
    res_creation = client.post(
        "/api/personnages", json={"nom": "X", "profil_visuel": "p"}, headers=entetes)
    identifiant = res_creation.json()["identifiant"]

    res = client.post(f"/api/personnages/{identifiant}/identite",
                      json={"fichier_cible": "/etc/passwd"}, headers=entetes)

    assert res.status_code == 403


def test_appliquer_identite_atteint_reellement_l_agent(client, entetes, monkeypatch):
    res_creation = client.post(
        "/api/personnages", json={"nom": "X", "profil_visuel": "p"}, headers=entetes)
    identifiant = res_creation.json()["identifiant"]

    fichier = MEDIA_DIR / "rendered" / "test_personnage_cible.jpg"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(b"scene")
    appels = []

    async def double(perso_id, fichier_cible, many_faces=False):
        appels.append((perso_id, fichier_cible, many_faces))
        return {"statut": "SUCCESS", "preuve": fichier_cible}

    monkeypatch.setattr(personnages.video_production_agent, "appliquer_identite_personnage", double)

    try:
        res = client.post(
            f"/api/personnages/{identifiant}/identite",
            json={"fichier_cible": str(fichier), "many_faces": True}, headers=entetes)

        assert res.status_code == 200
        assert appels == [(identifiant, str(fichier.resolve()), True)]
    finally:
        fichier.unlink(missing_ok=True)
