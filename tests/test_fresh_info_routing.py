"""Le chat va-t-il réellement chercher l'information sur le web ?

Ces tests parcourent la chaîne HTTP complète : routeur → agent → sources
renvoyées à l'appelant. Le modèle et le web sont doublés ; le reste est réel.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main

CLE = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE}"}

REPONSE_SOURCEE = {
    "status": "success",
    "agent": "FreshInfoAgent",
    "response": "Python 3.14 est la dernière version [1].",
    "sources_count": 1,
    "sources": [
        {"index": 1, "title": "Python 3.14", "url": "https://exemple.test/py",
         "characters": 120, "truncated": False},
    ],
    "unreadable": [],
}


async def _reponse_de_chat(user_input=None, context=None, **kw):
    """Réponse conversationnelle simulée : pas d'appel au modèle, pas de source."""
    return {"intent": "CHAT", "agent": "OrchestratorAgent", "response": "Bonjour."}


class AgentDouble:
    def __init__(self, reponse):
        self.reponse = reponse
        self.demandes = []

    async def run(self, user_input, context=None):
        self.demandes.append(user_input)
        return self.reponse


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "ARENA_API_KEY", CLE)
    monkeypatch.setattr(main, "REQUETES_MAX", 100)
    monkeypatch.setattr(main.limiteur, "requetes_max", 100)

    # `/api/chat` s'arrête avant tout agent si Ollama ne répond pas. C'est le
    # comportement voulu ; ici on veut mesurer l'aiguillage, pas cette garde.
    async def toujours_disponible():
        return True

    monkeypatch.setattr(main.fast_provider, "is_available", toujours_disponible)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def agent_double(monkeypatch) -> AgentDouble:
    double = AgentDouble(REPONSE_SOURCEE)
    monkeypatch.setattr(main, "fresh_agent", double)
    return double


@pytest.fixture
def intention(monkeypatch):
    """Force l'intention détectée, sans dépendre du modèle."""
    def _forcer(valeur):
        async def _classer(user_input):
            return valeur
        monkeypatch.setattr(main.orchestrator, "analyze_intent", _classer)
    return _forcer


# --- Mise en forme des sources -------------------------------------------------

def test_les_sources_sont_listees_sous_la_reponse():
    texte = main.formater_sources(REPONSE_SOURCEE["sources"])

    assert "**Sources**" in texte
    assert "[1] Python 3.14 — https://exemple.test/py" in texte


def test_sans_source_rien_n_est_ajoute():
    assert main.formater_sources([]) == ""


# --- /api/chat -----------------------------------------------------------------

def test_une_question_d_actualite_atteint_l_agent(client, agent_double, intention):
    intention("FRESH_INFO")

    res = client.post("/api/chat",
                      json={"prompt": "Quelle est la dernière version de Python ?"},
                      headers=ENTETES)

    assert res.status_code == 200
    assert agent_double.demandes == ["Quelle est la dernière version de Python ?"]


def test_les_sources_sont_renvoyees_a_l_appelant(client, agent_double, intention):
    intention("FRESH_INFO")

    corps = client.post("/api/chat", json={"prompt": "question"}, headers=ENTETES).json()

    assert corps["agent"] == "FreshInfoAgent"
    assert corps["sources"][0]["url"] == "https://exemple.test/py"


def test_l_intention_annoncee_est_celle_qui_a_ete_suivie(client, agent_double, intention):
    """Elle annonçait « CHAT » même quand un agent spécialisé avait répondu."""
    intention("FRESH_INFO")

    corps = client.post("/api/chat", json={"prompt": "question"}, headers=ENTETES).json()

    assert corps["intent"] == "FRESH_INFO"
    assert corps["agent"] == "FreshInfoAgent"


def test_une_conversation_ordinaire_ne_declenche_pas_de_recherche(
    client, agent_double, intention, monkeypatch
):
    intention("CHAT")
    monkeypatch.setattr(main.orchestrator, "run", _reponse_de_chat)

    client.post("/api/chat", json={"prompt": "Bonjour"}, headers=ENTETES)

    assert agent_double.demandes == []


def test_une_reponse_sans_source_expose_une_liste_vide(client, monkeypatch, intention):
    intention("CHAT")
    monkeypatch.setattr(main.orchestrator, "run", _reponse_de_chat)

    corps = client.post("/api/chat", json={"prompt": "Bonjour"}, headers=ENTETES).json()

    assert corps["status"] == "success"
    assert corps["sources"] == []


# --- Passerelle /v1 ------------------------------------------------------------

def test_le_modele_arena_fresh_est_propose_aux_interfaces(client):
    modeles = [m["id"] for m in client.get("/v1/models", headers=ENTETES).json()["data"]]

    assert "arena-fresh" in modeles


def test_arena_fresh_appelle_l_agent_et_cite_ses_sources(client, agent_double):
    res = client.post("/v1/chat/completions",
                      json={"model": "arena-fresh",
                            "messages": [{"role": "user", "content": "question"}]},
                      headers=ENTETES)

    contenu = res.json()["choices"][0]["message"]["content"]
    assert "Python 3.14 est la dernière version [1]." in contenu
    assert "https://exemple.test/py" in contenu
    assert agent_double.demandes == ["question"]


def test_arena_core_aiguille_aussi_vers_l_agent(client, agent_double, intention):
    intention("FRESH_INFO")

    res = client.post("/v1/chat/completions",
                      json={"model": "arena-core",
                            "messages": [{"role": "user", "content": "question"}]},
                      headers=ENTETES)

    assert "**Sources**" in res.json()["choices"][0]["message"]["content"]
    assert agent_double.demandes == ["question"]


def test_la_classification_n_est_pas_refaite_par_la_passerelle(client, agent_double, monkeypatch):
    """Elle coûte un appel au modèle : la refaire par requête serait du gaspillage."""
    appels = []

    async def _classer(user_input):
        appels.append(user_input)
        return "FRESH_INFO"

    monkeypatch.setattr(main.orchestrator, "analyze_intent", _classer)

    client.post("/v1/chat/completions",
                json={"model": "arena-core",
                      "messages": [{"role": "user", "content": "question"}]},
                headers=ENTETES)

    assert len(appels) == 1, f"classification faite {len(appels)} fois"
