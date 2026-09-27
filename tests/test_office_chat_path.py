"""Chemin utilisateur Office : PWA -> routeur -> Dioumtoukay."""

from pathlib import Path

import pytest

from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import ChatRequest, dispatch_request, sources_office_jointes


def test_seuls_les_fichiers_du_staging_office_sont_exposes_a_l_agent(
    tmp_path, monkeypatch,
):
    racine = tmp_path / "univer"
    staging = racine / "imports"
    staging.mkdir(parents=True)
    bon = staging / "budget.xlsx"
    bon.write_bytes(b"xlsx")
    dehors = tmp_path / "secret.xlsx"
    dehors.write_bytes(b"xlsx")
    mauvais = staging / "payload.exe"
    mauvais.write_bytes(b"MZ")
    monkeypatch.setattr(routeur_chat, "UNIVER_WORKSPACE_DIR", racine)

    resultat = sources_office_jointes(
        [str(bon), str(dehors), str(mauvais), str(staging / "absent.xlsx")]
    )

    assert resultat == [str(bon.resolve())]


@pytest.mark.asyncio
async def test_atelier_recoit_le_fichier_office_du_tour_courant(
    tmp_path, monkeypatch,
):
    racine = tmp_path / "univer"
    staging = racine / "imports"
    staging.mkdir(parents=True)
    source = staging / "budget.xlsx"
    source.write_bytes(b"xlsx")
    monkeypatch.setattr(routeur_chat, "UNIVER_WORKSPACE_DIR", racine)

    appels = []

    async def run(prompt, context=None):
        appels.append((prompt, context))
        return {
            "status": "success",
            "response": "Fichier Office pris en charge.",
            "actions": [],
        }

    monkeypatch.setattr(routeur_chat.dioumtoukay_agent, "run", run)

    resultat = await dispatch_request(
        ChatRequest(
            prompt="Modifie ce fichier Excel.",
            office_paths=[str(source)],
        ),
        intent="ATELIER",
    )

    assert resultat["response"] == "Fichier Office pris en charge."
    assert appels == [
        (
            "Modifie ce fichier Excel.",
            {
                "session_id": "default",
                "office_paths": [str(source.resolve())],
            },
        )
    ]
