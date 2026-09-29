"""Le point d'aiguillage transmet réellement l'ancrage aux agents visés."""
import pytest

from apps.backend.routers import chat


class AgentSonde:
    def __init__(self):
        self.recu = None

    async def run(self, question, context=None):
        self.recu = question
        return {"status": "success", "agent": "sonde", "response": "mesuré"}


@pytest.mark.asyncio
async def test_aiguillage_relit_le_fil_en_memoire(monkeypatch):
    sonde = AgentSonde()
    monkeypatch.setattr(chat, "researcher_agent", sonde)
    monkeypatch.setattr(chat.memory, "get_recent_history", lambda **_: [
        {"role": "user", "content": "Parle-moi du football sénégalais"},
        {"role": "assistant", "content": "D'accord."},
    ])

    await chat._aiguiller(
        chat.ChatRequest(prompt="donne-moi un nom", session_id="conversation-1"),
        "DEEP_RESEARCH",
    )

    assert sonde.recu == (
        "donne-moi un nom\n\nSujet du tour précédent : football sénégalais"
    )


@pytest.mark.asyncio
async def test_panne_memoire_ne_fait_pas_tomber_la_reponse(monkeypatch):
    sonde = AgentSonde()
    monkeypatch.setattr(chat, "researcher_agent", sonde)

    def panne(**_):
        raise RuntimeError("mémoire indisponible")

    monkeypatch.setattr(chat.memory, "get_recent_history", panne)
    resultat = await chat._aiguiller(
        chat.ChatRequest(prompt="donne-moi un nom", session_id="conversation-1"),
        "DEEP_RESEARCH",
    )

    assert resultat["response"] == "mesuré"
    assert sonde.recu == "donne-moi un nom"


@pytest.mark.asyncio
async def test_intention_de_fichier_n_est_jamais_ancree(monkeypatch):
    sonde = AgentSonde()
    monkeypatch.setattr(chat, "vision_agent", sonde)
    monkeypatch.setattr(chat.memory, "get_recent_history", lambda **_: [
        {"role": "user", "content": "Parle-moi du football"},
    ])

    await chat._aiguiller(chat.ChatRequest(prompt="analyse-la"), "VISION")

    assert sonde.recu == "analyse-la"
