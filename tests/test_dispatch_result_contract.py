import pytest

from apps.backend.routers import chat


class _Agent:
    def __init__(self, resultat):
        self.resultat = resultat

    async def run(self, *args, **kwargs):
        return self.resultat


@pytest.mark.asyncio
async def test_aiguillage_isole_un_resultat_non_dict(monkeypatch):
    monkeypatch.setattr(chat, "coder_agent", _Agent(None))
    monkeypatch.setattr(chat.memory, "add_chat_message", lambda **kwargs: None)

    resultat = await chat._aiguiller(
        chat.ChatRequest(prompt="execute ce code", session_id="contrat"),
        "CODE_EXECUTION",
    )

    assert resultat["status"] == "error"
    assert resultat["intent"] == "CODE_EXECUTION"
    assert "resultat interne invalide" in resultat["response"]


@pytest.mark.asyncio
async def test_aiguillage_transforme_reponse_absente_en_erreur(monkeypatch):
    monkeypatch.setattr(chat, "coder_agent", _Agent({"status": "success", "agent": "Coder"}))
    monkeypatch.setattr(chat.memory, "add_chat_message", lambda **kwargs: None)

    resultat = await chat._aiguiller(
        chat.ChatRequest(prompt="execute ce code", session_id="contrat"),
        "CODE_EXECUTION",
    )

    assert resultat["status"] == "error"
    assert resultat["intent"] == "CODE_EXECUTION"
    assert "n'a produit aucune" in resultat["response"]


@pytest.mark.asyncio
async def test_aiguillage_preserve_une_reponse_valide(monkeypatch):
    attendu = {"status": "success", "agent": "Coder", "response": "termine"}
    monkeypatch.setattr(chat, "coder_agent", _Agent(attendu))
    monkeypatch.setattr(chat.memory, "add_chat_message", lambda **kwargs: None)

    resultat = await chat._aiguiller(
        chat.ChatRequest(prompt="execute ce code", session_id="contrat"),
        "CODE_EXECUTION",
    )

    assert resultat["status"] == "success"
    assert resultat["response"] == "termine"
    assert resultat["intent"] == "CODE_EXECUTION"
