"""Contrôle des fichiers envoyés à `/api/upload`.

Trois choses sont vérifiées, pas une : le type accepté, la taille plafonnée, et
le fait qu'un envoi refusé ne laisse rien sur le disque.
"""
import io

import pytest
from fastapi.testclient import TestClient

from apps.backend import main

CLE_DE_TEST = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE_DE_TEST}"}


@pytest.fixture
def dossier_media(tmp_path, monkeypatch):
    """Redirige `media/` vers un dossier temporaire : les tests n'écrivent pas dans le dépôt."""
    monkeypatch.setattr(main, "MEDIA_DIR", tmp_path / "media")
    return tmp_path / "media" / "incoming"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "ARENA_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


def envoyer(client, nom, contenu=b"contenu binaire"):
    return client.post(
        "/api/upload",
        files={"file": (nom, io.BytesIO(contenu), "application/octet-stream")},
        headers=ENTETES,
    )


# --- Types acceptés et refusés -------------------------------------------------

@pytest.mark.parametrize("nom", ["clip.mp4", "prise.MOV", "son.wav", "piste.m4a", "film.mkv"])
def test_un_media_est_accepte(client, dossier_media, nom):
    res = envoyer(client, nom)

    assert res.status_code == 200, res.json()
    assert res.json()["status"] == "success"
    assert (dossier_media / nom).exists()


@pytest.mark.parametrize("nom", ["virus.exe", "script.ps1", "payload.sh", "note.txt", "page.html"])
def test_un_fichier_non_media_est_refuse(client, dossier_media, nom):
    res = envoyer(client, nom)

    assert res.status_code == 415
    assert not (dossier_media / nom).exists()


def test_un_fichier_sans_extension_est_refuse(client, dossier_media):
    assert envoyer(client, "sans_extension").status_code == 415


def test_une_double_extension_est_jugee_sur_la_derniere(client, dossier_media):
    """`clip.mp4.exe` est un exécutable, pas une vidéo."""
    assert envoyer(client, "clip.mp4.exe").status_code == 415


def test_un_nom_vide_est_refuse(client, dossier_media):
    assert envoyer(client, "").status_code in {400, 415, 422}


# --- Traversée de répertoire ---------------------------------------------------

def test_un_chemin_remontant_est_neutralise(client, dossier_media, tmp_path):
    res = envoyer(client, "../../../evade.mp4")

    assert res.status_code == 200
    assert (dossier_media / "evade.mp4").exists()
    assert not (tmp_path.parent / "evade.mp4").exists()


# --- Taille --------------------------------------------------------------------

def test_un_fichier_trop_gros_est_refuse(client, dossier_media, monkeypatch):
    monkeypatch.setattr(main, "TAILLE_MAX_ENVOI", 1024)  # 1 Ko

    res = envoyer(client, "trop_gros.mp4", contenu=b"x" * 5000)

    assert res.status_code == 413
    assert "trop volumineux" in res.json()["detail"].lower()


def test_un_fichier_refuse_pour_sa_taille_ne_laisse_rien_sur_le_disque(
    client, dossier_media, monkeypatch
):
    monkeypatch.setattr(main, "TAILLE_MAX_ENVOI", 1024)

    envoyer(client, "trop_gros.mp4", contenu=b"x" * 5000)

    assert not (dossier_media / "trop_gros.mp4").exists()


def test_un_fichier_juste_sous_le_plafond_passe(client, dossier_media, monkeypatch):
    monkeypatch.setattr(main, "TAILLE_MAX_ENVOI", 1024)

    res = envoyer(client, "limite.mp4", contenu=b"x" * 1024)

    assert res.status_code == 200
    assert res.json()["size_bytes"] == 1024


def test_un_fichier_vide_est_refuse(client, dossier_media):
    res = envoyer(client, "vide.mp4", contenu=b"")

    assert res.status_code == 400
    assert not (dossier_media / "vide.mp4").exists()


# --- Écriture par blocs --------------------------------------------------------

class FichierEspion:
    """Double d'`UploadFile` qui note la taille demandée à chaque lecture."""

    def __init__(self, contenu: bytes):
        self._contenu = contenu
        self._position = 0
        self.tailles_demandees = []

    async def read(self, size=-1):
        self.tailles_demandees.append(size)
        if size is None or size < 0:
            morceau = self._contenu[self._position:]
            self._position = len(self._contenu)
        else:
            morceau = self._contenu[self._position:self._position + size]
            self._position += len(morceau)
        return morceau


async def test_le_fichier_est_lu_par_blocs_et_non_d_un_seul_coup(tmp_path):
    """Le point de la correction : `await file.read()` sans argument chargeait tout en mémoire."""
    contenu = b"y" * (3 * 1024 * 1024 + 17)   # 3 Mo et des poussières
    espion = FichierEspion(contenu)
    destination = tmp_path / "gros.mp4"

    taille = await main.ecrire_par_blocs(espion, destination)

    assert taille == len(contenu)
    assert destination.read_bytes() == contenu
    # Une lecture par bloc, plus la lecture vide qui termine la boucle.
    assert espion.tailles_demandees == [main.TAILLE_BLOC_ENVOI] * 5
    assert -1 not in espion.tailles_demandees, "un read() sans limite charge tout en mémoire"


async def test_le_plafond_arrete_la_lecture_sans_lire_tout_le_fichier(tmp_path, monkeypatch):
    """Un fichier de 8 Go ne doit pas être lu en entier avant d'être refusé."""
    monkeypatch.setattr(main, "TAILLE_MAX_ENVOI", 2 * main.TAILLE_BLOC_ENVOI)
    espion = FichierEspion(b"z" * (10 * 1024 * 1024))
    destination = tmp_path / "trop_gros.mp4"

    with pytest.raises(main.HTTPException) as erreur:
        await main.ecrire_par_blocs(espion, destination)

    assert erreur.value.status_code == 413
    assert len(espion.tailles_demandees) == 3, "la lecture aurait dû s'arrêter au 3e bloc"
    assert not destination.exists()


def test_le_contenu_ecrit_est_identique_a_l_original(client, dossier_media):
    contenu = bytes(range(256)) * 8192  # 2 Mo, donc plusieurs blocs

    res = envoyer(client, "fidele.mp4", contenu=contenu)

    assert res.status_code == 200
    assert (dossier_media / "fidele.mp4").read_bytes() == contenu


# --- Permissions et authentification ------------------------------------------

def test_sans_permission_d_ecriture_rien_n_est_ecrit(client, dossier_media, monkeypatch):
    monkeypatch.setattr(main.permissions, "is_allowed", lambda nom: False)

    res = envoyer(client, "clip.mp4")

    assert res.status_code == 403
    assert not (dossier_media / "clip.mp4").exists()


def test_sans_cle_api_rien_n_est_ecrit(client, dossier_media):
    res = client.post(
        "/api/upload",
        files={"file": ("clip.mp4", io.BytesIO(b"contenu"), "video/mp4")},
    )

    assert res.status_code == 401
    assert not (dossier_media / "clip.mp4").exists()
