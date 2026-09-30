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


class MoteurDocumentaireSonde:
    """Respecte le contrat minimal de LightRAGTool pour ce test."""

    def __init__(self):
        self.questions = []

    def query(self, question, mode="hybrid"):
        self.questions.append(question)
        return "réponse"


@pytest.mark.asyncio
async def test_un_vieux_indexe_mes_documents_ne_fait_pas_basculer_une_question(monkeypatch):
    """Le fil est du contexte, jamais une entrée pour le routage d'ARENA.

    Un tour passé qui disait « indexe mes documents » ne doit pas faire
    prendre la branche indexation à une question sans rapport, seulement
    parce que ce mot réapparaît dans le bloc de contexte joint (régression
    trouvée en faisant tourner la suite complète, jamais un seul fichier de
    test à la fois).
    """
    moteur = MoteurDocumentaireSonde()
    monkeypatch.setattr(chat, "lightrag_tool", moteur)
    monkeypatch.setattr(chat.memory, "get_fact", lambda *_: "Ousmane")
    monkeypatch.setattr(chat.memory, "get_recent_history", lambda **_: [
        {"role": "user", "content": "Indexe mes documents"},
        {"role": "assistant", "content": "Indexation terminée."},
    ])

    resultat = await chat._aiguiller(
        chat.ChatRequest(prompt="quel est le prix du BA13 ?", session_id="conversation-2"),
        "RAG_DOCS",
    )

    assert resultat["agent"] == "LightRAG"
    assert moteur.questions and moteur.questions[0].endswith(
        f"{DEBUT_DEMANDE}\nquel est le prix du BA13 ?"
    )


@pytest.mark.asyncio
async def test_un_vieux_design_system_ne_fait_pas_basculer_une_recherche(monkeypatch):
    """Même règle pour DESIGN_UI : la capacité se décide sur la demande

    actuelle, jamais sur un mot du fil joint.
    """
    from core.actions.resultat import ResultatAction, Statut

    appels = []

    def _executer(nom_service, capacite, **kw):
        appels.append((capacite, kw.get("requete")))
        return ResultatAction(statut=Statut.SUCCES, action=capacite,
                              cible=nom_service, message="ok", preuve="ok")

    monkeypatch.setattr(chat.registre, "executer", _executer)
    monkeypatch.setattr(chat.memory, "get_fact", lambda *_: "Ousmane")
    monkeypatch.setattr(chat.memory, "get_recent_history", lambda **_: [
        {"role": "user", "content": "propose-moi un design system complet"},
        {"role": "assistant", "content": "Système proposé."},
    ])

    await chat._aiguiller(
        chat.ChatRequest(prompt="et pour les icônes ?", session_id="conversation-3"),
        "DESIGN_UI",
    )

    assert appels[0][0] == "chercher"
    assert appels[0][1].endswith(f"{DEBUT_DEMANDE}\net pour les icônes ?")
