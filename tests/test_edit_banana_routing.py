"""Tests de routage d'intention pour la capacité DrawIO vs vision ordinaire."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from apps.backend import main
from apps.backend import security as securite
from apps.backend.runtime import registre
from core.actions.resultat import succes
from core.production.conversion.demande import format_de_conversion

DRAWIO_REQUESTS = [
    "Transform this image into an editable DrawIO file.",
    "Make this diagram editable.",
    "Convert this architecture diagram to DrawIO.",
    "Turn this screenshot into an editable diagram.",
    "Recreate this flowchart as an editable DrawIO.",
    "Transforme cette image en diagramme DrawIO modifiable.",
    "Rends ce schéma éditable.",
    "Convertis ce diagramme d'architecture en DrawIO.",
    "Recrée ce flowchart en DrawIO.",
    "Convertis ce schéma en drawio",
]

VISION_REQUESTS = [
    "What does this diagram mean?",
    "Analyse ce schéma.",
    "Que montre ce diagramme ?",
    "Décris cette image.",
    "Lis le texte de cette image.",
    "Que vois-tu sur cette capture d'écran ?",
    "Analyse ce plan de construction.",
]


@pytest.mark.parametrize("demande", DRAWIO_REQUESTS)
def test_demande_drawio_reconnue_comme_conversion(demande):
    format_cible = format_de_conversion(demande)
    assert format_cible == "drawio", f"Échec d'extraction de format DrawIO pour: {demande}"

    intention = OrchestratorAgent._classer_par_mots_cles(None, demande)
    assert intention == "CONVERSION", f"L'intention attendue pour '{demande}' était CONVERSION, reçu: {intention}"


@pytest.mark.parametrize("demande", VISION_REQUESTS)
def test_demande_vision_reste_sur_vision(demande):
    format_cible = format_de_conversion(demande)
    assert format_cible is None, f"Une question de vision ne doit pas être vue comme conversion: {demande}"

    intention = OrchestratorAgent._classer_par_mots_cles(None, demande)
    assert intention == "VISION", f"L'intention attendue pour '{demande}' était VISION, reçu: {intention}"


def _fake_png_diagram() -> bytes:
    tampon = io.BytesIO()
    img = Image.new("RGB", (200, 100), color=(240, 240, 240))
    img.save(tampon, format="PNG")
    return tampon.getvalue()


def test_workflow_conversion_drawio_avec_piece_jointe(monkeypatch, tmp_path):
    cle = "cle-test-edit-banana"
    monkeypatch.setattr(securite, "USMAN_API_KEY", cle)

    dossier_sorties = tmp_path / "rendered" / "conversions"
    dossier_sorties.mkdir(parents=True, exist_ok=True)
    fichier_drawio = dossier_sorties / "diagram-res.drawio"
    fichier_drawio.write_text(
        '<mxfile><diagram><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel></diagram></mxfile>',
        encoding="utf-8",
    )

    def mock_convertir(*args, **kwargs):
        return succes(
            "convertir",
            "file_conversion",
            message=f"Document « {fichier_drawio.name} » converti via edit-banana.",
            preuve=str(fichier_drawio),
            url=f"/media/rendered/conversions/{fichier_drawio.name}",
            format_cible="drawio",
            taille_apres_octets=fichier_drawio.stat().st_size,
            moteur="edit-banana",
        )

    connecteur_fc = registre.obtenir("file_conversion")
    assert connecteur_fc is not None
    monkeypatch.setattr(connecteur_fc, "_convertir_un_fichier", mock_convertir)

    client = TestClient(main.app)
    entetes = {"Authorization": f"Bearer {cle}"}

    depot = client.post(
        "/files",
        headers=entetes,
        files={"file": ("architecture.png", _fake_png_diagram(), "image/png")},
        data={"kind": "image"},
    )
    assert depot.status_code == 200
    identifiant = depot.json()["id"]

    flux = client.post(
        "/agent/stream",
        headers=entetes,
        json={
            "text": "Transform this image into an editable DrawIO file.",
            "attachments": [identifiant],
            "run_id": "test-drawio-flow",
            "conversation_id": "test-drawio-flow",
        },
    )
    assert flux.status_code == 200
    assert "drawio" in flux.text.lower() or "architecture" in flux.text.lower()
