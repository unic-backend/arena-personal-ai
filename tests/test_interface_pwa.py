"""L'interface servie sur `/` : la PWA quand elle est compilee, l'ancienne sinon.

`apps/pwa/dist/` est ignore par Git. Un depot fraichement clone ne contient donc
pas la PWA compilee, et servir un chemin absent rendrait une page blanche sans
dire pourquoi. Ces tests tiennent les deux cas, et le fait que `/health` annonce
laquelle repond.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main


@pytest.fixture
def client() -> TestClient:
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def pwa_compilee(tmp_path, monkeypatch):
    """Simule une PWA compilee, sans dependre de l'etat du poste."""
    fichier = tmp_path / "index.html"
    fichier.write_text("<html><body>PWA ARENA</body></html>", encoding="utf-8")
    monkeypatch.setattr(main, "INTERFACE_PWA", fichier)
    return fichier


@pytest.fixture
def pwa_absente(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "INTERFACE_PWA", tmp_path / "jamais_compilee.html")


# --- La PWA prend la place quand elle existe ----------------------------------

def test_la_pwa_compilee_est_servie_sur_la_racine(client, pwa_compilee):
    res = client.get("/")

    assert res.status_code == 200
    assert "PWA ARENA" in res.text


def test_l_interface_servie_est_la_pwa_quand_elle_existe(pwa_compilee):
    assert main.interface_servie() == pwa_compilee
    assert main.nom_interface() == "pwa"


# --- L'ancienne repond quand la PWA n'est pas compilee ------------------------

def test_sans_pwa_compilee_l_ancienne_interface_repond(client, pwa_absente):
    """Un depot fraichement clone doit rester utilisable."""
    res = client.get("/")

    assert res.status_code == 200
    assert res.text.strip() != ""


def test_l_interface_servie_retombe_sur_la_classique(pwa_absente):
    assert main.interface_servie() == main.INTERFACE_CLASSIQUE
    assert main.nom_interface() == "classique"


# --- L'ancienne n'est jamais perdue -------------------------------------------

def test_l_ancienne_interface_reste_joignable_meme_avec_la_pwa(client, pwa_compilee):
    """Retirer ce qui marche pour installer ce qui est neuf n'est pas un progres."""
    res = client.get("/ui/classique")

    assert res.status_code == 200
    assert "PWA ARENA" not in res.text


def test_l_ancienne_interface_existe_bien_dans_le_depot():
    assert main.INTERFACE_CLASSIQUE.exists()


# --- /health dit laquelle repond, sans deviner --------------------------------

def test_health_annonce_la_pwa(client, pwa_compilee):
    assert client.get("/health").json()["interface"] == "pwa"


def test_health_annonce_la_classique(client, pwa_absente):
    """Une interface manquante est un etat annonce, pas une panne silencieuse."""
    assert client.get("/health").json()["interface"] == "classique"


def test_le_chemin_de_la_pwa_est_celui_que_vite_produit():
    """`vite build` ecrit dans `dist/` : le serveur regarde exactement la."""
    assert main.INTERFACE_PWA.parts[-3:] == ("pwa", "dist", "index.html")


# --- La PWA n'a besoin de rien d'autre ----------------------------------------

def test_la_pwa_est_servie_telle_quelle_sans_assets(client, pwa_compilee):
    """`vite-plugin-singlefile` inline tout : un seul fichier suffit."""
    res = client.get("/")

    assert res.headers["content-type"].startswith("text/html")
    assert res.text == pwa_compilee.read_text(encoding="utf-8")
