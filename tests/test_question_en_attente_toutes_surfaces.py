"""La question en attente vaut sur TOUTES les surfaces, pas seulement `/api/chat`.

**Mesuré le 26/09/2026.** La règle « une réponse à une question d'ARENA revient
à l'agent qui l'a posée » (`tests/test_question_en_attente.py`) ne vivait que
dans `dispatch_request`, et seulement quand l'appelant n'avait pas déjà classé.
Or la PWA, la passerelle OpenAI et `/api/chat/stream` classent elles-mêmes et
passent l'intention. Reproduit par la vraie route `/agent/stream` : question du
devis notée pour la session, « Medina » envoyé depuis le téléphone —
`dispatch_request` recevait `FRESH_INFO`. La question était notée après chaque
tour, et relue par personne sur le chemin que le propriétaire emprunte.

Chaque test ci-dessous donne au classeur une réponse FAUSSE (`FRESH_INFO`) :
s'il est consulté, le test le voit.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import chat as module_chat
from apps.backend.routers import openai_gateway as passerelle
from apps.backend.routers import pwa_gateway
from core.executive import question_en_attente as q

CLE = "cle-de-test-question-en-attente"
DEVIS_INCOMPLET = {"statut": "INCOMPLET", "manquants": ["lieu"]}


@pytest.fixture(autouse=True)
def memoire_vierge():
    q.tout_oublier()
    yield
    q.tout_oublier()


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE}"}


@pytest.fixture
def classeur_faux(monkeypatch):
    """Un classeur qui se trompe, et qui note chaque fois qu'on le consulte."""
    appels = []

    async def _faux(texte, espace=None):
        appels.append(texte)
        return "FRESH_INFO"

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", _faux)
    return appels


def _espion_du_dispatch(monkeypatch, module):
    vues = []

    async def _espion(requete, intent=None, **_options):
        vues.append(intent)
        return {"response": "ok", "agent": "espion", "sources": []}

    monkeypatch.setattr(module, "dispatch_request", _espion)
    return vues


def test_la_pwa_rend_medina_au_devis(client, entetes, classeur_faux, monkeypatch):
    vues = _espion_du_dispatch(monkeypatch, pwa_gateway)
    conversation = f"conv-{uuid4()}"
    q.noter(conversation, "PLAQUISTE", DEVIS_INCOMPLET)

    client.post("/agent/stream", headers=entetes, json={
        "text": "Medina", "conversation_id": conversation, "run_id": f"run-{uuid4()}"})

    assert vues == ["PLAQUISTE"], "le telephone envoyait « Medina » a la recherche web"
    assert classeur_faux == [], "le classeur a ete consulte alors qu'une question attendait"


def test_la_pwa_classe_normalement_sans_question(client, entetes, classeur_faux, monkeypatch):
    vues = _espion_du_dispatch(monkeypatch, pwa_gateway)

    client.post("/agent/stream", headers=entetes, json={
        "text": "Medina", "conversation_id": f"conv-{uuid4()}", "run_id": f"run-{uuid4()}"})

    assert vues == ["FRESH_INFO"]
    assert classeur_faux == ["Medina"]


def test_la_passerelle_openai_rend_medina_au_devis(client, entetes, classeur_faux, monkeypatch):
    vues = _espion_du_dispatch(monkeypatch, passerelle)
    fil = [
        {"role": "user", "content": "Fais-moi un devis du nom de Khady Diop"},
        {"role": "assistant", "content": "D'accord."},
        {"role": "user", "content": "Medina"},
    ]
    q.noter(passerelle._cle_de_conversation(fil), "PLAQUISTE", DEVIS_INCOMPLET)

    client.post("/v1/chat/completions", headers=entetes, json={
        "model": "usman-chat", "stream": False, "messages": fil})

    assert vues == ["PLAQUISTE"]
    assert classeur_faux == []


def test_le_flux_api_chat_rend_medina_au_devis(client, entetes, classeur_faux, monkeypatch):
    vues = _espion_du_dispatch(monkeypatch, module_chat)
    q.noter("session-flux", "PLAQUISTE", DEVIS_INCOMPLET)

    reponse = client.post("/api/chat/stream", headers=entetes, json={
        "prompt": "Medina", "session_id": "session-flux"})

    assert vues == ["PLAQUISTE"]
    assert classeur_faux == []
    premiere = next(ligne for ligne in reponse.text.splitlines() if ligne.startswith("data:"))
    assert json.loads(premiere[5:])["intent"] == "PLAQUISTE"
