"""Contrôle des fichiers envoyés à `/api/upload`.

Trois choses sont vérifiées, pas une : le type accepté, la taille plafonnée, et
le fait qu'un envoi refusé ne laisse rien sur le disque.
"""
import io

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import media

CLE_DE_TEST = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE_DE_TEST}"}


@pytest.fixture
def dossier_media(tmp_path, monkeypatch):
    """Redirige `media/` vers un dossier temporaire : les tests n'écrivent pas dans le dépôt."""
    monkeypatch.setattr(media, "MEDIA_DIR", tmp_path / "media")
    return tmp_path / "media" / "incoming"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
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


@pytest.mark.parametrize("nom", ["photo.jpg", "cliche.PNG", "capture.webp"])
def test_une_photo_est_acceptee(client, dossier_media, nom):
    """Ouvert le 02/09/2026 : la capacite « vision » du projet Video lit une
    image (agents/video/production_agent.py:_appeler_vision), mais jusqu'ici
    aucune photo n'atteignait jamais MEDIA_DIR — le seul point d'entree la
    refusait, sans exception, quel que soit l'appelant."""
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


@pytest.mark.parametrize("envoye, attendu", [
    ("C:\\Users\\Saer\\clip.mp4", "clip.mp4"),
    ("..\\..\\evade.mp4", "evade.mp4"),
    ("dossier\\sous-dossier\\video.mp4", "video.mp4"),
    ("../../evade.mp4", "evade.mp4"),
    ("normal.mp4", "normal.mp4"),
])
def test_un_chemin_windows_est_coupe_comme_un_chemin_posix(envoye, attendu):
    """Le proprietaire est sous Windows, le serveur sous Linux : le `\\` n'y est
    pas un separateur, donc « C:\\Users\\Saer\\clip.mp4 » revenait ENTIER et
    devenait un nom de fichier absurde dans `incoming/`. `pieces_jointes.py`
    avait deja resolu ce cas ; cette route ne le reutilisait pas. Trouve en
    revue le 31/08/2026.

    Teste sur la fonction, pas via HTTP : le transport multipart peut
    lui-meme transformer le nom, et un test qui passe grace a ca ne prouve
    rien sur ce que fait la route."""
    assert media.valider_nom_de_fichier(envoye) == attendu


def test_un_chemin_windows_remontant_est_neutralise(client, dossier_media):
    res = envoyer(client, "..\\..\\evade.mp4")

    assert res.status_code == 200
    assert (dossier_media / "evade.mp4").exists()


# --- Taille --------------------------------------------------------------------

def test_un_fichier_trop_gros_est_refuse(client, dossier_media, monkeypatch):
    monkeypatch.setattr(media, "TAILLE_MAX_ENVOI", 1024)  # 1 Ko

    res = envoyer(client, "trop_gros.mp4", contenu=b"x" * 5000)

    assert res.status_code == 413
    assert "trop volumineux" in res.json()["detail"].lower()


def test_un_fichier_refuse_pour_sa_taille_ne_laisse_rien_sur_le_disque(
    client, dossier_media, monkeypatch
):
    monkeypatch.setattr(media, "TAILLE_MAX_ENVOI", 1024)

    envoyer(client, "trop_gros.mp4", contenu=b"x" * 5000)

    assert not (dossier_media / "trop_gros.mp4").exists()


def test_un_fichier_juste_sous_le_plafond_passe(client, dossier_media, monkeypatch):
    monkeypatch.setattr(media, "TAILLE_MAX_ENVOI", 1024)

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

    taille = await media.ecrire_par_blocs(espion, destination)

    assert taille == len(contenu)
    assert destination.read_bytes() == contenu
    # Une lecture par bloc, plus la lecture vide qui termine la boucle.
    assert espion.tailles_demandees == [media.TAILLE_BLOC_ENVOI] * 5
    assert -1 not in espion.tailles_demandees, "un read() sans limite charge tout en mémoire"


async def test_le_plafond_arrete_la_lecture_sans_lire_tout_le_fichier(tmp_path, monkeypatch):
    """Un fichier de 8 Go ne doit pas être lu en entier avant d'être refusé."""
    monkeypatch.setattr(media, "TAILLE_MAX_ENVOI", 2 * media.TAILLE_BLOC_ENVOI)
    espion = FichierEspion(b"z" * (10 * 1024 * 1024))
    destination = tmp_path / "trop_gros.mp4"

    with pytest.raises(media.HTTPException) as erreur:
        await media.ecrire_par_blocs(espion, destination)

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
    monkeypatch.setattr(media.permissions, "is_allowed", lambda nom: False)

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


# --- Collision de noms ---------------------------------------------------------
# Avant ce correctif (audit externe, commit f7f0478) : `ecrire_par_blocs`
# ouvrait `destination` en `"wb"`, qui TRONQUE un fichier deja present des
# l'ouverture — un deuxieme envoi du meme nom effacait le premier avant meme
# de savoir si le sien allait reussir, et un echec ensuite supprimait meme ce
# qui restait (le fichier partage n'existait plus du tout).

def test_un_deuxieme_envoi_du_meme_nom_ne_detruit_pas_le_premier(client, dossier_media):
    premier = envoyer(client, "chantier.mp4", contenu=b"PREMIER CONTENU REEL")
    assert premier.status_code == 200
    assert premier.json()["filename"] == "chantier.mp4"

    second = envoyer(client, "chantier.mp4", contenu=b"SECOND CONTENU DIFFERENT")
    assert second.status_code == 200
    assert second.json()["filename"] == "chantier_1.mp4", (
        "le second envoi n'a pas ete renomme : il a du ecraser le premier")
    assert second.json()["original_filename"] == "chantier.mp4"

    # Les DEUX fichiers existent, avec chacun leur VRAI contenu — ni l'un ni
    # l'autre n'a ete tronque ou efface par l'autre.
    assert (dossier_media / "chantier.mp4").read_bytes() == b"PREMIER CONTENU REEL"
    assert (dossier_media / "chantier_1.mp4").read_bytes() == b"SECOND CONTENU DIFFERENT"


def test_un_troisieme_envoi_du_meme_nom_prend_le_numero_suivant(client, dossier_media):
    envoyer(client, "chantier.mp4", contenu=b"un")
    envoyer(client, "chantier.mp4", contenu=b"deux")
    troisieme = envoyer(client, "chantier.mp4", contenu=b"trois")

    assert troisieme.json()["filename"] == "chantier_2.mp4"
    assert (dossier_media / "chantier.mp4").read_bytes() == b"un"
    assert (dossier_media / "chantier_1.mp4").read_bytes() == b"deux"
    assert (dossier_media / "chantier_2.mp4").read_bytes() == b"trois"


def test_un_nom_different_n_est_jamais_renomme(client, dossier_media):
    """La grande majorite des envois ne collisionnent jamais : le nom
    d'origine doit rester lisible, pas un identifiant genere par defaut."""
    reponse = envoyer(client, "reunion_chantier.mp4")
    assert reponse.json()["filename"] == "reunion_chantier.mp4"
    assert reponse.json()["original_filename"] == "reunion_chantier.mp4"


def test_un_envoi_qui_echoue_apres_collision_ne_touche_pas_le_premier(
    client, dossier_media, monkeypatch
):
    """Le second envoi (renomme `chantier_1.mp4`) echoue pour sa propre
    raison (taille) — le PREMIER fichier, sous son propre nom, doit rester
    intact : le nettoyage d'un echec ne doit jamais toucher un chemin qu'il
    n'a pas lui-meme ouvert."""
    premier = envoyer(client, "chantier.mp4", contenu=b"contenu du premier")
    assert premier.status_code == 200

    monkeypatch.setattr(media, "TAILLE_MAX_ENVOI", 4)  # tout depasse ce plafond
    second = envoyer(client, "chantier.mp4", contenu=b"un contenu bien trop long")
    assert second.status_code == 413

    assert (dossier_media / "chantier.mp4").read_bytes() == b"contenu du premier"
    assert not (dossier_media / "chantier_1.mp4").exists()


async def test_ecrire_par_blocs_ne_touche_jamais_un_fichier_deja_present(tmp_path):
    """Le mecanisme central, isole de la route : `open(..., "xb")` refuse
    d'ecrire quand `destination` existe deja, AVANT de lire le moindre
    octet du nouvel envoi — le contenu existant reste bit pour bit
    identique."""
    destination = tmp_path / "partage.mp4"
    destination.write_bytes(b"contenu original, jamais touche")

    espion = FichierEspion(b"contenu du nouvel envoi, jamais ecrit")
    with pytest.raises(FileExistsError):
        await media.ecrire_par_blocs(espion, destination)

    assert destination.read_bytes() == b"contenu original, jamais touche"
    assert espion.tailles_demandees == [], (
        "le nouvel envoi a ete lu alors que la reclamation du fichier a echoue")


def test_deux_envois_reellement_concurrents_du_meme_nom_ne_se_marchent_pas_dessus(
    client, dossier_media,
):
    """Pas une simulation sequentielle : deux VRAIS threads envoient
    `chantier.mp4` en meme temps. Avant ce correctif, le `"wb"` de
    `ecrire_par_blocs` n'offrait aucune garantie d'exclusion — deux
    ecritures concurrentes pouvaient entrelacer leurs blocs dans le MEME
    fichier, ou l'une ecraser silencieusement l'autre."""
    import concurrent.futures

    contenu_a = b"A" * (256 * 1024)
    contenu_b = b"B" * (256 * 1024)

    def _envoyer(contenu):
        return envoyer(client, "chantier.mp4", contenu=contenu)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executeur:
        futur_a = executeur.submit(_envoyer, contenu_a)
        futur_b = executeur.submit(_envoyer, contenu_b)
        reponse_a = futur_a.result()
        reponse_b = futur_b.result()

    assert reponse_a.status_code == 200 and reponse_b.status_code == 200
    noms = {reponse_a.json()["filename"], reponse_b.json()["filename"]}
    assert noms == {"chantier.mp4", "chantier_1.mp4"}, (
        f"les deux envois concurrents n'ont pas obtenu deux noms distincts : {noms}")

    # Chaque fichier ecrit porte un contenu ENTIER et COHERENT — jamais un
    # melange des deux blocs entrelaces, jamais l'un vide parce que l'autre
    # l'a rouvert en "wb" par-dessus.
    contenus_sur_disque = {
        (dossier_media / "chantier.mp4").read_bytes(),
        (dossier_media / "chantier_1.mp4").read_bytes(),
    }
    assert contenus_sur_disque == {contenu_a, contenu_b}
