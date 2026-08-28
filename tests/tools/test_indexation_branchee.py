"""« Indexe mes documents » — la phrase atteint-elle vraiment l'indexeur ?

`tools/documents/indexer.py` et `tools/documents/inventory.py` sont testés pour
eux-mêmes ailleurs. Ce fichier tient le **branchement** : la demande arrive par
le chemin documentaire du chat, l'indexation tourne réellement, et une question
ordinaire ne déclenche rien.

Aucun test n'appelle Ollama : le moteur documentaire est un double qui respecte
le contrat de `LightRAGTool` (`insert_text(texte) -> bool`).
"""
import threading

import httpx
import pytest

from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import (
    ChatRequest,
    demande_d_indexation,
    dispatch_request,
    indexer_ses_documents,
)
from tools.documents import indexer as indexeur


class MoteurDouble:
    """Respecte le contrat de LightRAGTool, sans Ollama."""

    def __init__(self, accepte=True):
        self.accepte = accepte
        self.textes = []
        self.fils = []
        self.questions = []

    def insert_text(self, texte: str) -> bool:
        # Le fil est note pour prouver que l indexation ne tourne pas sur la
        # boucle du serveur.
        self.fils.append(threading.current_thread() is threading.main_thread())
        self.textes.append(texte)
        return self.accepte

    def query(self, question, mode="hybrid"):
        self.questions.append(question)
        return "reponse de l index"


@pytest.fixture
def classeur(tmp_path):
    dossier = tmp_path / "documents"
    dossier.mkdir()
    (dossier / "devis.txt").write_text("Devis 2026-041, cloison BA13.", encoding="utf-8")
    (dossier / "notes.md").write_text("Chantier Almadies, 12 m2.", encoding="utf-8")
    return dossier


@pytest.fixture
def inventaire(tmp_path):
    return tmp_path / "inventaire.json"


async def indexer(moteur, classeur, inventaire, verifier=False):
    return await indexer_ses_documents(moteur=moteur, dossier=classeur,
                                       inventaire=inventaire, verifier=verifier)


# --- La demande fait tourner l'indexeur -------------------------------------------

async def test_la_demande_indexe_reellement_les_documents(classeur, inventaire):
    moteur = MoteurDouble()

    resultat = await indexer(moteur, classeur, inventaire)

    assert len(moteur.textes) == 2, "les deux documents lisibles doivent être insérés"
    assert resultat["indexation"]["indexes"] == 2
    assert resultat["agent"] == "IndexeurDocuments"


async def test_l_indexation_ne_tourne_pas_sur_la_boucle(classeur, inventaire):
    """Elle lit des fichiers et fait travailler Ollama : sur la boucle, tout gèle."""
    moteur = MoteurDouble()

    await indexer(moteur, classeur, inventaire)

    assert moteur.fils and not any(moteur.fils), (
        "l'indexation doit tourner hors du fil principal")


async def test_relancer_la_demande_ne_reindexe_rien(classeur, inventaire):
    """L'inventaire est bien dans la chaîne : un fichier inchangé n'est pas repris."""
    moteur = MoteurDouble()

    await indexer(moteur, classeur, inventaire)
    second = await indexer(moteur, classeur, inventaire)

    assert len(moteur.textes) == 2, "le GPU ne doit pas retravailler sur du déjà-vu"
    assert second["indexation"]["statut"] == "RIEN_A_FAIRE"
    assert "déjà indexés" in second["response"] or "deja indexes" in second["response"]


async def test_un_document_ajoute_est_repris(classeur, inventaire):
    moteur = MoteurDouble()
    await indexer(moteur, classeur, inventaire)

    (classeur / "facture.txt").write_text("Facture 2026-050.", encoding="utf-8")
    second = await indexer(moteur, classeur, inventaire)

    assert second["indexation"]["indexes"] == 1
    assert len(moteur.textes) == 3


# --- Ce qui n'est pas fait, et ce qui n'est pas dit --------------------------------

async def test_sans_ollama_rien_n_est_indexe_et_la_commande_est_donnee(
        classeur, inventaire, monkeypatch):
    def refuse(*args, **kwargs):
        raise httpx.ConnectError("connexion refusee")

    monkeypatch.setattr(httpx, "get", refuse)
    moteur = MoteurDouble()

    resultat = await indexer(moteur, classeur, inventaire, verifier=True)

    assert resultat["indexation"]["statut"] == "REFUSE"
    assert moteur.textes == [], "rien ne doit être indexé sans moteur d'embeddings"
    assert "ollama serve" in resultat["response"]


async def test_le_message_ne_livre_pas_le_contenu_des_documents(classeur, inventaire):
    """Ces fichiers portent des noms de clients, des montants et des chantiers."""
    moteur = MoteurDouble()

    resultat = await indexer(moteur, classeur, inventaire)

    assert "Almadies" not in resultat["response"]
    assert "BA13" not in resultat["response"]


# --- L'aiguillage : indexer ou interroger ? ---------------------------------------

@pytest.mark.parametrize("phrase", [
    "Indexe mes documents",
    "indexer mes documents s'il te plaît",
    "réindexe le classeur",
    "mets à jour mes documents",
])
def test_les_phrases_d_indexation_sont_reconnues(phrase):
    assert demande_d_indexation(phrase)


@pytest.mark.parametrize("phrase", [
    "D'après mes documents, quel est le prix du BA13 ?",
    "Qu'est-ce qu'il y a dans mes devis ?",
])
def test_une_question_n_est_pas_une_demande_d_indexation(phrase):
    assert not demande_d_indexation(phrase)


async def test_le_routeur_indexe_sur_demande(monkeypatch, classeur, inventaire):
    """La chaîne complète : phrase → routeur → inventaire → lecture → moteur."""
    moteur = MoteurDouble()
    monkeypatch.setattr(routeur_chat, "lightrag_tool", moteur)
    monkeypatch.setattr(routeur_chat, "DOSSIER_DOCUMENTS", classeur)
    monkeypatch.setattr(routeur_chat, "FICHIER_INVENTAIRE", inventaire)
    # Le moteur d embeddings est le seul maillon qui exige Ollama : il est
    # declare pret, le reste de la chaine est reel.
    monkeypatch.setattr(indexeur, "verifier_moteur", lambda *a, **k: None)

    resultat = await dispatch_request(
        ChatRequest(prompt="Indexe mes documents", session_id="test"), intent="RAG_DOCS")

    assert resultat["agent"] == "IndexeurDocuments"
    assert len(moteur.textes) == 2, "les documents doivent être insérés par ce chemin"
    assert inventaire.exists(), "l'inventaire doit garder trace de ce qui est indexé"
    assert moteur.questions == [], "une demande d'indexation n'interroge pas l'index"


async def test_le_routeur_interroge_l_index_pour_une_question(monkeypatch):
    moteur = MoteurDouble()
    monkeypatch.setattr(routeur_chat, "lightrag_tool", moteur)

    resultat = await dispatch_request(
        ChatRequest(prompt="D'après mes documents, quel est le prix du BA13 ?",
                    session_id="test"),
        intent="RAG_DOCS")

    assert resultat["agent"] == "LightRAG"
    assert moteur.questions and moteur.textes == []


@pytest.mark.parametrize("phrase", [
    "Indexe mes documents",
    "indexer mes documents",
    "mets à jour mes documents",
])
def test_le_repli_hors_ligne_envoie_la_demande_au_moteur_documentaire(phrase):
    """Sans Ollama pour classer, la demande doit quand même atteindre l'indexeur."""
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    assert OrchestratorAgent._classer_par_mots_cles(None, phrase) == "RAG_DOCS"
