"""`/media/rendered/{nom:path}` doit servir les sorties imbriquees des
conversions, sans jamais affaiblir le confinement dans `media/`.

Avant ce correctif (audit externe, commit f7f0478) :
`core/connectors/file_conversion.py` rend des URL comme
`/media/rendered/conversions/devis.pdf`, mais la route ne declarait qu'un
seul segment (`{nom}`) — FastAPI ne fait meme pas correspondre un chemin
contenant `/` a ce gabarit : 404 avant d'atteindre `validate_media_path`.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.config import RENDERED_DIR

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


@pytest.fixture
def fichier_imbrique():
    chemin = RENDERED_DIR / "conversions" / "devis_test_route.pdf"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(b"%PDF-1.4 contenu fictif")
    try:
        yield chemin
    finally:
        chemin.unlink(missing_ok=True)


@pytest.fixture
def fichier_plat():
    chemin = RENDERED_DIR / "rendu_test_route.mp4"
    chemin.write_bytes(b"contenu video fictif")
    try:
        yield chemin
    finally:
        chemin.unlink(missing_ok=True)


class TestFichierImbrique:
    def test_un_fichier_imbrique_est_servi_via_son_url_reelle(
        self, client, entetes, fichier_imbrique,
    ):
        reponse = client.get("/media/rendered/conversions/devis_test_route.pdf",
                             headers=entetes)
        assert reponse.status_code == 200
        assert reponse.content == b"%PDF-1.4 contenu fictif"

    def test_sans_cle_un_fichier_imbrique_reste_refuse(self, client, fichier_imbrique):
        reponse = client.get("/media/rendered/conversions/devis_test_route.pdf")
        assert reponse.status_code == 401

    def test_la_cle_en_parametre_marche_aussi_pour_un_chemin_imbrique(
        self, client, fichier_imbrique,
    ):
        reponse = client.get(
            f"/media/rendered/conversions/devis_test_route.pdf?cle={CLE_DE_TEST}")
        assert reponse.status_code == 200


class TestFichierPlatInchange:
    """La compatibilite avec l'ancien comportement (fichier sans sous-dossier)."""

    def test_un_fichier_plat_reste_servi_normalement(self, client, entetes, fichier_plat):
        reponse = client.get("/media/rendered/rendu_test_route.mp4", headers=entetes)
        assert reponse.status_code == 200
        assert reponse.content == b"contenu video fictif"


class TestConfinementPreserve:
    """`{nom:path}` change ce que la route ACCEPTE en entree, jamais ce que
    `validate_media_path` verifie apres — la traversee reste refusee,
    imbriquee ou non."""

    @pytest.mark.parametrize("cible", [
        "../../etc/passwd",
        "conversions/../../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
    ])
    def test_une_traversee_est_refusee(self, client, entetes, cible):
        reponse = client.get(f"/media/rendered/{cible}", headers=entetes)
        assert reponse.status_code in (403, 404), (
            f"une tentative de traversee ({cible!r}) n'a pas ete refusee : "
            f"{reponse.status_code}")

    def test_un_fichier_absent_reste_un_404_jamais_un_500(self, client, entetes):
        reponse = client.get("/media/rendered/conversions/n_existe_pas.pdf",
                             headers=entetes)
        assert reponse.status_code == 404
