"""Un document se télécharge, un média se lit sur place.

**Mesuré le 21/09/2026, capture d'écran du propriétaire** : un devis PDF
ouvert depuis son téléphone s'ouvrait dans la visionneuse du navigateur —
jamais proposé au téléchargement.

`FileResponse` (Starlette) ne pose **aucun** `Content-Disposition` quand
`filename` n'est pas fourni — c'est alors le navigateur qui décide, et Chrome
mobile choisit d'afficher un PDF plutôt que de le sauvegarder. Ce fichier
couvre `type_de_presentation()` (le classement) et la route elle-même (le
branchement, mesuré par-dessus un vrai `TestClient`).
"""
from __future__ import annotations

import pytest

from apps.backend.security import EXTENSIONS_EN_LIGNE, type_de_presentation

# --- Le classement -----------------------------------------------------------

@pytest.mark.parametrize("nom", [
    "devis.pdf", "rapport.docx", "grille.xlsx", "presentation.pptx",
    "notes.md", "brouillon.txt", "page.html", "archive.zip",
    "fichier_sans_extension", "SUFFIXE.PDF",
])
def test_un_document_se_telecharge(nom: str) -> None:
    assert type_de_presentation(nom) == "attachment"


@pytest.mark.parametrize("nom", [
    "clip.mp4", "montage.mov", "audio.mp3", "voix.wav",
    "photo.png", "photo.JPG", "logo.svg", "GIF.gif",
])
def test_un_media_reste_en_ligne(nom: str) -> None:
    assert type_de_presentation(nom) == "inline"


def test_la_liste_en_ligne_ne_couvre_que_video_audio_image() -> None:
    """Un document ne doit jamais se glisser dans la liste des exceptions —
    ce serait rouvrir exactement le défaut mesuré."""
    for suffixe in EXTENSIONS_EN_LIGNE:
        assert suffixe not in {".pdf", ".docx", ".xlsx", ".pptx", ".odt",
                               ".txt", ".md", ".html", ".zip", ".csv"}


# --- La route, sur un vrai serveur --------------------------------------------

@pytest.fixture()
def client(monkeypatch):
    """Le vrai `app`, la vraie `RENDERED_DIR` — jamais rechargés.

    Recharger `apps.backend.main` casse le serveur (500 mesure) : le module
    initialise des singletons a l'import (moteurs, registre) que recharger
    dedouble. Ecrire dans un sous-dossier jetable de la VRAIE `RENDERED_DIR`
    exerce exactement le chemin que le telephone emprunte, sans y toucher.
    """
    import uuid

    from apps.backend.config import RENDERED_DIR
    from apps.backend.main import app

    cle = "cle-de-test-media-route"
    monkeypatch.setattr("apps.backend.security.USMAN_API_KEY", cle)

    dossier = RENDERED_DIR / f"test-telechargement-{uuid.uuid4().hex[:8]}"
    dossier.mkdir(parents=True)
    try:
        from fastapi.testclient import TestClient
        yield TestClient(app), dossier, cle
    finally:
        import shutil
        shutil.rmtree(dossier, ignore_errors=True)


def test_un_pdf_recoit_un_content_disposition_attachment(client) -> None:
    app_client, dossier, cle = client
    (dossier / "devis.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

    reponse = app_client.get(f"/media/rendered/{dossier.name}/devis.pdf?cle={cle}")

    assert reponse.status_code == 200
    assert reponse.headers.get("content-disposition") == 'attachment; filename="devis.pdf"'


def test_une_video_ne_recoit_toujours_aucun_content_disposition(client) -> None:
    """Le comportement d'avant, préservé au caractère près : un `<video src>`
    ne doit jamais recevoir d'en-tête qui le ferait télécharger au lieu de
    jouer."""
    app_client, dossier, cle = client
    (dossier / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")

    reponse = app_client.get(f"/media/rendered/{dossier.name}/clip.mp4?cle={cle}")

    assert reponse.status_code == 200
    assert "content-disposition" not in {k.lower() for k in reponse.headers}


def test_un_document_dans_un_sous_dossier_recoit_aussi_l_en_tete(client) -> None:
    """Les conversions écrivent sous `conversions/…` — le classement suit le
    nom du fichier, pas sa profondeur."""
    app_client, dossier, cle = client
    sous_dossier = dossier / "conversions"
    sous_dossier.mkdir()
    (sous_dossier / "rapport.docx").write_bytes(b"PK\x03\x04")

    reponse = app_client.get(
        f"/media/rendered/{dossier.name}/conversions/rapport.docx?cle={cle}")

    assert reponse.status_code == 200
    assert reponse.headers.get("content-disposition") == 'attachment; filename="rapport.docx"'
