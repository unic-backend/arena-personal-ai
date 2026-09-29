"""Le point d'aiguillage transmet réellement tout le fil récent aux agents."""
import pytest

from apps.backend.routers import chat
from core.context.ancrage import DEBUT_CONTEXTE, DEBUT_DEMANDE, FIN_CONTEXTE


class AgentSonde:
    def __init__(self):
        self.recu = None

    async def run(self, question, context=None):
        self.recu = question
        return {"status": "success", "agent": "sonde", "response": "mesuré"}


@pytest.mark.parametrize(("ancien", "demande"), [
    pytest.param("Parle-moi du football sénégalais", "donne-moi un nom", id="sport"),
    pytest.param("Explique-moi le cours du Bitcoin", "donne-moi un chiffre", id="economie"),
    pytest.param("Je cherche un livre de Mariama Bâ", "un titre", id="culture"),
    pytest.param("Prépare le chantier de Pikine", "combien", id="travail"),
    pytest.param("Comparons Python et Rust", "le plus rapide", id="informatique"),
])
@pytest.mark.asyncio
async def test_chaque_domaine_arrive_avec_son_fil(monkeypatch, ancien, demande):
    sonde = AgentSonde()
    monkeypatch.setattr(chat, "researcher_agent", sonde)
    monkeypatch.setattr(chat.memory, "get_fact", lambda *_: "Ousmane")
    monkeypatch.setattr(chat.memory, "get_recent_history", lambda **_: [
        {"role": "user", "content": ancien},
        {"role": "assistant", "content": "D'accord."},
    ])

    await chat._aiguiller(
        chat.ChatRequest(prompt=demande, session_id="conversation-1"),
        "DEEP_RESEARCH",
    )

    assert sonde.recu == "\n".join((
        DEBUT_CONTEXTE,
        f"Ousmane: {ancien}",
        "Usman: D'accord.",
        FIN_CONTEXTE,
        DEBUT_DEMANDE,
        demande,
    ))


@pytest.mark.asyncio
async def test_une_demande_avec_son_sujet_reste_la_demande_actuelle(monkeypatch):
    sonde = AgentSonde()
    monkeypatch.setattr(chat, "researcher_agent", sonde)
    monkeypatch.setattr(chat.memory, "get_fact", lambda *_: "Ousmane")
    demande = "parle-moi du basket"
    historique = [{"role": "user", "content": "Parlons de football"}]

    await chat._aiguiller(
        chat.ChatRequest(prompt=demande, history=historique), "DEEP_RESEARCH"
    )

    assert sonde.recu.endswith(f"{DEBUT_DEMANDE}\n{demande}")
    assert f"{DEBUT_CONTEXTE}\nOusmane: Parlons de football" in sonde.recu


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
async def test_intention_de_fichier_ne_recoit_pas_le_fil(monkeypatch):
    sonde = AgentSonde()
    monkeypatch.setattr(chat, "vision_agent", sonde)
    monkeypatch.setattr(chat.memory, "get_recent_history", lambda **_: [
        {"role": "user", "content": "Parle-moi du football"},
    ])

    await chat._aiguiller(chat.ChatRequest(prompt="analyse-la"), "VISION")

    assert sonde.recu == "analyse-la"
