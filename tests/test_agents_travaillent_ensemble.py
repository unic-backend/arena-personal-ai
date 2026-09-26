"""Les agents travaillent ensemble sur une demande qui en nomme plusieurs.

Demande du proprietaire, 26/09/2026 : « tous les agents doivent pouvoir
travailler ensemble — aucun agent n'est prisonnier de ses capacites ».
Mesure avant ce correctif : chaque demande a deux metiers partait chez UN
agent, qui ne faisait que sa part. Ces tests passent par le vrai
`dispatch_request` et la vraie route du telephone ; seuls le classeur et les
agents sont remplaces, pour ne pas dependre d'un modele.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import chat as module_chat
from core.agent import equipe
from core.executive import question_en_attente

CLE = "cle-de-test-equipe"
DEVIS = "Devis DV-7 : 30 m2 de cloison, 360 000 F."
PHRASE = "fais un devis de 30 m2 de cloison et envoie-le par mail à khady@exemple.com"


@pytest.fixture(autouse=True)
def etat_vierge():
    equipe.oublier_les_plans()
    question_en_attente.tout_oublier()
    yield
    equipe.oublier_les_plans()
    question_en_attente.tout_oublier()


@pytest.fixture
def agents(monkeypatch):
    """Classeur et agents scriptes ; le reste du chemin est le vrai."""
    async def classer(texte, espace=None):
        if texte.startswith("envoie"):
            return "EMAIL"
        return "PLAQUISTE"

    appels = []

    async def aiguiller(requete, intention):
        appels.append((intention, requete.prompt))
        texte = DEVIS if intention == "PLAQUISTE" else "Mail pret, a confirmer."
        return {"status": "success", "agent": intention, "response": texte,
                "intent": intention}

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", classer)
    monkeypatch.setattr(module_chat, "_aiguiller", aiguiller)
    return appels


async def test_dispatch_fait_travailler_le_devis_puis_le_courrier(agents):
    rendu = await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE, session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)

    assert [intention for intention, _ in agents] == ["PLAQUISTE", "EMAIL"]
    assert DEVIS in agents[1][1], "l'agent courrier doit recevoir le devis"
    assert DEVIS in rendu["response"] and "Mail pret" in rendu["response"]


async def test_une_reponse_attendue_ne_se_decoupe_pas(agents):
    session = f"s-{uuid4()}"
    question_en_attente.noter(session, "PLAQUISTE",
                              {"statut": "INCOMPLET", "manquants": ["lieu"]})

    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE, session_id=session),
        intent="PLAQUISTE", consigner_le_tour=False)

    assert [intention for intention, _ in agents] == ["PLAQUISTE"]


def test_le_telephone_fait_travailler_l_equipe(agents, monkeypatch):
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    client = TestClient(main.app, raise_server_exceptions=False)

    client.post("/agent/stream", headers={"Authorization": f"Bearer {CLE}"}, json={
        "text": PHRASE, "conversation_id": f"conv-{uuid4()}", "run_id": f"run-{uuid4()}"})

    assert [intention for intention, _ in agents] == ["PLAQUISTE", "EMAIL"]
