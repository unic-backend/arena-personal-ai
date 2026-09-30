"""Restauration et comprehension d'image gardent deux semantiques distinctes."""
import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from apps.backend import main
from apps.backend import security as securite
from apps.backend.config import RENDERED_DIR
from apps.backend.routers import pwa_gateway
from apps.backend.routers.pwa_gateway import _documents_produits
from apps.backend.runtime import image_restoration_agent, pieces_jointes
from core.restoration.codeformer import ResultatRestauration


@pytest.mark.parametrize("demande", [
    "Restaure cette vieille photo.",
    "Ameliore ce portrait endommage.",
    "Enhance the faces in this image.",
    "Restaure cette photo et ameliore l'arriere-plan.",
])
def test_une_demande_de_restauration_va_a_codeformer(demande):
    intention = OrchestratorAgent._classer_par_mots_cles(None, demande)
    assert intention == "IMAGE_RESTORATION"


@pytest.mark.parametrize("demande", [
    "Que montre cette photo ?",
    "Decris cette image.",
    "Lis le texte de cette image.",
])
def test_la_comprehension_d_image_reste_sur_vision(demande):
    intention = OrchestratorAgent._classer_par_mots_cles(None, demande)
    assert intention == "VISION"


def test_le_rendu_image_emprunte_le_canal_d_artefact_existant():
    produits = _documents_produits({
        "document": {
            "statut": "SUCCESS", "url": "/media/rendered/restorations/r.png",
            "message": "Image restauree", "type": "image/png",
        }
    })
    assert produits == [{
        "url": "/media/rendered/restorations/r.png", "action": "produire",
        "message": "Image restauree", "type": "image/png",
    }]


def _png_reel() -> bytes:
    tampon = io.BytesIO()
    Image.effect_noise((64, 64), 70).convert("RGB").save(tampon, format="PNG")
    return tampon.getvalue()


def test_workflow_pwa_upload_restauration_et_artefact_authentifie(monkeypatch):
    """Le vrai chemin HTTP/SSE, avec seule l'inference lourde doublee."""
    cle = "cle-codeformer-test"
    monkeypatch.setattr(securite, "USMAN_API_KEY", cle)

    async def classer(*_args, **_kwargs):
        return "IMAGE_RESTORATION"

    monkeypatch.setattr(pwa_gateway, "classer_la_demande", classer)
    original = _png_reel()
    digest = hashlib.sha256(original).hexdigest()
    sortie = RENDERED_DIR / "restorations" / "workflow-codeformer-test.png"
    provenance = sortie.with_suffix(".png.json")

    async def inference_doublee(contenu, **parametres):
        assert hashlib.sha256(contenu).hexdigest() == digest
        sortie.parent.mkdir(parents=True, exist_ok=True)
        Image.effect_noise((128, 128), 85).convert("RGB").save(sortie, format="PNG")
        provenance.write_text('{"operation":"image_restoration"}', encoding="utf-8")
        return ResultatRestauration(
            sortie=sortie, url="/media/rendered/restorations/workflow-codeformer-test.png",
            provenance=provenance, largeur=128, hauteur=128,
            taille_octets=sortie.stat().st_size, fidelity=parametres["fidelity"],
            background_enhancement=parametres["background_enhancement"],
            device="cpu", duree_secondes=0.01, source_sha256=digest,
        )

    monkeypatch.setattr(image_restoration_agent.service, "restaurer", inference_doublee)
    client = TestClient(main.app)
    entetes = {"Authorization": f"Bearer {cle}"}
    try:
        depot = client.post(
            "/files", headers=entetes,
            files={"file": ("portrait.png", original, "image/png")},
            data={"kind": "image"},
        )
        assert depot.status_code == 200
        identifiant = depot.json()["id"]

        flux = client.post("/agent/stream", headers=entetes, json={
            "text": "Restaure cette photo", "attachments": [identifiant],
            "run_id": "workflow-codeformer", "conversation_id": "workflow-codeformer",
        })
        assert flux.status_code == 200
        charges = [json.loads(ligne.removeprefix("data: "))
                   for ligne in flux.text.splitlines() if ligne.startswith("data: ")]
        fin = next(charge for charge in charges if charge.get("type") == "done")
        assert fin["meta"]["documents"][0]["type"] == "image/png"
        assert fin["meta"]["documents"][0]["url"].endswith("workflow-codeformer-test.png")

        piece = pieces_jointes.lire(identifiant)
        assert piece is not None
        assert hashlib.sha256(piece.octets_originaux() or b"").hexdigest() == digest
        rendu = client.get(fin["meta"]["documents"][0]["url"], headers=entetes)
        assert rendu.status_code == 200
        with Image.open(io.BytesIO(rendu.content)) as image:
            image.verify()
    finally:
        sortie.unlink(missing_ok=True)
        provenance.unlink(missing_ok=True)
