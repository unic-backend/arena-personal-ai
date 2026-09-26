"""Un tour d'agent spécialisé entre UNE fois dans le fil, avec SA phrase.

**Mesuré le 26/09/2026**, par la vraie route `/agent/stream` : après
« Medina » (réponse à la question du lieu d'un devis), `short_term_memory`
contenait quatre lignes au lieu de deux —

    user      | Ousmane: Fais-moi un devis… / Usman: Quel est le lieu… / Ousmane: Medina / Usman:
    assistant | Quel est le lieu du chantier ?
    user      | Medina
    assistant | Quel est le lieu du chantier ?

Deux défauts : `_aiguiller` écrivait `request.prompt`, qui est le fil ENTIER
aplati pour PLAQUISTE (la PWA et la passerelle OpenAI l'y mettent), et la PWA
consignait le même tour une seconde fois. Le fil se recopiait dans lui-même et
remplissait la fenêtre de six tours relus au tour suivant.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import chat as module_chat
from apps.backend.routers import openai_gateway as passerelle
from core.executive import question_en_attente

CLE = "cle-de-test-fil-ecrit-une-fois"
QUESTION = "Quel est le lieu du chantier ?"


@pytest.fixture(autouse=True)
def memoire_vierge():
    question_en_attente.tout_oublier()
    yield
    question_en_attente.tout_oublier()


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE}"}


@pytest.fixture
def plaquiste_qui_demande(monkeypatch):
    """Le classeur dit PLAQUISTE ; l'agent repond une question, sans modele."""
    async def _plaquiste(*_a, **_k):
        return "PLAQUISTE"

    async def _run(*_a, **_k):
        return {"response": QUESTION}

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", _plaquiste)
    monkeypatch.setattr(module_chat.plaquiste_agent, "run", _run)


def _fil(session: str) -> list:
    return [(tour["role"], tour["content"])
            for tour in module_chat.memory.get_recent_history(session_id=session, limit=20)]


def test_la_pwa_ecrit_le_tour_une_fois_avec_sa_phrase(client, entetes, plaquiste_qui_demande):
    conversation = f"conv-{uuid4()}"
    historique = [
        {"role": "user", "content": "Fais-moi un devis du nom de Khady Diop"},
        {"role": "assistant", "content": QUESTION},
    ]

    client.post("/agent/stream", headers=entetes, json={
        "text": "Medina", "conversation_id": conversation,
        "run_id": f"run-{uuid4()}", "history": historique})

    assert _fil(conversation) == [("user", "Medina"), ("assistant", QUESTION)]


def test_la_passerelle_openai_ecrit_sa_phrase_pas_le_fil(client, entetes, plaquiste_qui_demande):
    messages = [
        {"role": "user", "content": "Fais-moi un devis du nom de Khady Diop"},
        {"role": "assistant", "content": QUESTION},
        {"role": "user", "content": "Medina"},
    ]

    client.post("/v1/chat/completions", headers=entetes, json={
        "model": "usman-chat", "stream": False, "messages": messages})

    assert _fil(passerelle._cle_de_conversation(messages)) == [
        ("user", "Medina"), ("assistant", QUESTION)]


def test_api_chat_ecrit_toujours_le_tour(client, entetes, plaquiste_qui_demande, monkeypatch):
    """Sans appelant qui consigne lui-meme, `dispatch_request` le fait."""
    async def _disponible():
        return True
    monkeypatch.setattr(module_chat.fast_provider, "is_available", _disponible)
    session = f"api-{uuid4()}"

    client.post("/api/chat", headers=entetes, json={"prompt": "Medina", "session_id": session})

    assert _fil(session) == [("user", "Medina"), ("assistant", QUESTION)]
