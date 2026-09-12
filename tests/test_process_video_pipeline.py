"""`/api/process-video` n'annonce plus un succes sur un rendu qui n'existe pas.

Avant ce correctif (audit externe, commit f7f0478) : `convert_to_vertical_9_16`
peut rendre `False` (ffmpeg indisponible, rendu tronque) sans jamais lever —
et son retour etait completement ignore ici. La reponse annoncait
`"status": "success"` avec une `video_web_url` qui pointait sur un fichier
absent ou invalide.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.config import MEDIA_DIR, RENDERED_DIR
from apps.backend.routers import media as routeur_media

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


@pytest.fixture
def video_source():
    """Un fichier reel sous MEDIA_DIR (controle de chemin de la route) —
    son contenu n'a pas besoin d'etre un vrai mp4, `convert_to_vertical_9_16`
    est monkeypatche dans chaque test ci-dessous."""
    fichier = MEDIA_DIR / "incoming" / "test_process_video_pipeline.mp4"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(b"faux contenu mp4")
    try:
        yield fichier
    finally:
        fichier.unlink(missing_ok=True)
        cible = RENDERED_DIR / f"{fichier.stem}_vertical_9_16.mp4"
        cible.unlink(missing_ok=True)


def _sans_clip_existant(monkeypatch):
    """Force le chemin `convert_to_vertical_9_16` : aucun clip deja pret."""
    async def _video(prompt, context=None):
        return {"segments": []}
    async def _clip(prompt, context=None):
        return {"clip_path": None}
    async def _sub(prompt, context=None):
        return {"srt_path": ""}
    monkeypatch.setattr(routeur_media.video_agent, "run", _video)
    monkeypatch.setattr(routeur_media.clip_selector, "run", _clip)
    monkeypatch.setattr(routeur_media.subtitle_agent, "run", _sub)


def test_un_rendu_qui_echoue_devient_une_erreur_pas_un_succes(
    client, entetes, monkeypatch, video_source,
):
    _sans_clip_existant(monkeypatch)
    # `convert_to_vertical_9_16` rend False (ffmpeg indisponible ou rendu
    # tronque) SANS lever — exactement ce que le code ignorait avant.
    monkeypatch.setattr(
        routeur_media.editor_agent.crop_tool, "convert_to_vertical_9_16",
        lambda entree, sortie: False)

    reponse = client.post("/api/process-video", data={"video_path": str(video_source)},
                          headers=entetes)

    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["status"] == "error", (
        f"un rendu qui a echoue est rapporte comme un succes : {corps}")
    assert "video_web_url" not in corps


def test_un_fichier_ecrit_mais_vide_reste_une_erreur(
    client, entetes, monkeypatch, video_source,
):
    """`convert_to_vertical_9_16` pourrait un jour rendre True sur un
    fichier vide (bug different, meme famille) : la route elle-meme
    revalide, jamais une confiance aveugle dans le booleen recu."""
    _sans_clip_existant(monkeypatch)

    def _ecrit_vide(entree, sortie):
        Path(sortie).parent.mkdir(parents=True, exist_ok=True)
        Path(sortie).write_bytes(b"")
        return True
    monkeypatch.setattr(
        routeur_media.editor_agent.crop_tool, "convert_to_vertical_9_16", _ecrit_vide)

    reponse = client.post("/api/process-video", data={"video_path": str(video_source)},
                          headers=entetes)

    assert reponse.json()["status"] == "error"


def test_un_rendu_reussi_reste_annonce_normalement(
    client, entetes, monkeypatch, video_source,
):
    _sans_clip_existant(monkeypatch)

    def _reussi(entree, sortie):
        Path(sortie).parent.mkdir(parents=True, exist_ok=True)
        Path(sortie).write_bytes(b"contenu mp4 non vide")
        return True
    monkeypatch.setattr(
        routeur_media.editor_agent.crop_tool, "convert_to_vertical_9_16", _reussi)

    reponse = client.post("/api/process-video", data={"video_path": str(video_source)},
                          headers=entetes)

    corps = reponse.json()
    assert corps["status"] == "success"
    assert corps["video_web_url"].endswith("_vertical_9_16.mp4")
