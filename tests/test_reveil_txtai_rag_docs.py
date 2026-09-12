"""`txtai_search` reveille : le repli documentaire de LightRAG.

Un des cinq connecteurs qu'aucun chemin d'execution n'atteignait
(`tests/test_connecteurs_dormants.py`, DEC-0051). Sa raison de dormir etait
precise : il exige les TEXTES dans l'appel (`documents=[...]`) et ne lit
jamais le disque lui-meme, donc personne ne lui en fournissait jamais.

Reveille le 12/09/2026, a la demande du proprietaire : sur l'intention
`RAG_DOCS`, quand LightRAG ne repond pas, ses documents reels sont lus par
le meme `tools/documents/reader.py` que l'indexation, puis passes a txtai.

Ce que ces tests refusent de laisser passer : un repli qui rendrait une
reponse vide plutot qu'un echec honnete.
"""
import pytest

from apps.backend.routers import chat as routeur_chat


@pytest.fixture
def dossier_documents(tmp_path, monkeypatch):
    """Deux vrais fichiers .txt, lus par le vrai lecteur de documents."""
    (tmp_path / "chantier.txt").write_text(
        "Le chantier Fast Group a recu 234 plaques BA13 le 12 mars.",
        encoding="utf-8")
    (tmp_path / "devis.txt").write_text(
        "Devis UC-2026-0804 : cloison 72/48, 18 metres lineaires.",
        encoding="utf-8")
    monkeypatch.setattr(routeur_chat, "DOSSIER_DOCUMENTS", tmp_path)
    return tmp_path


@pytest.fixture
def lightrag_muet(monkeypatch):
    """LightRAG indisponible — le cas reel sur une machine sans Ollama."""
    monkeypatch.setattr(routeur_chat.lightrag_tool, "query",
                        lambda *a, **k: "LightRAG n'est pas disponible.")
    monkeypatch.setattr(routeur_chat, "lightrag_echec", lambda _reponse: True)


async def test_lightrag_muet_interroge_txtai_avec_ses_vrais_documents(
    dossier_documents, lightrag_muet, monkeypatch,
):
    recus = {}

    def _executer(nom, capacite, **parametres):
        recus["appel"] = (nom, capacite)
        recus["documents"] = parametres.get("documents")
        recus["requete"] = parametres.get("requete")
        return {"statut": "SUCCESS", "message": "1 passage trouve : 234 plaques BA13.",
                "detail": {"resultats": [{"score": 0.9}]}}
    monkeypatch.setattr(routeur_chat.registre, "executer", _executer)

    resultat = await routeur_chat.dispatch_request(
        routeur_chat.ChatRequest(prompt="combien de plaques pour Fast Group ?"),
        intent="RAG_DOCS")

    assert recus.get("appel") == ("txtai_search", "rechercher"), (
        f"txtai n'a pas ete appele : {recus}")
    assert any("234 plaques" in texte for texte in recus["documents"]), (
        "les textes passes a txtai ne viennent pas de ses vrais documents")
    assert recus["requete"] == "combien de plaques pour Fast Group ?"
    assert resultat["status"] == "success"
    assert resultat["agent"] == "txtai"
    assert "234 plaques" in resultat["response"]


async def test_un_dossier_vide_garde_l_echec_de_lightrag(
    tmp_path, lightrag_muet, monkeypatch,
):
    """Rien a chercher n'est pas une reponse : le message d'echec du chemin
    principal doit rester visible, jamais un resultat vide."""
    monkeypatch.setattr(routeur_chat, "DOSSIER_DOCUMENTS", tmp_path)
    appels = []
    monkeypatch.setattr(routeur_chat.registre, "executer",
                        lambda *a, **k: appels.append(a) or {"statut": "SUCCESS"})

    resultat = await routeur_chat.dispatch_request(
        routeur_chat.ChatRequest(prompt="que disent mes documents ?"),
        intent="RAG_DOCS")

    assert appels == [], "txtai a ete appele sans aucun document a lui donner"
    assert resultat["status"] == "error"
    assert resultat["agent"] == "LightRAG"


async def test_txtai_indisponible_garde_aussi_l_echec_de_lightrag(
    dossier_documents, lightrag_muet, monkeypatch,
):
    """Le repli du repli : txtai absent ne doit pas fabriquer un succes."""
    monkeypatch.setattr(routeur_chat.registre, "executer",
                        lambda *a, **k: {"statut": "ECHEC",
                                         "message": "txtai n'est pas installe."})

    resultat = await routeur_chat.dispatch_request(
        routeur_chat.ChatRequest(prompt="que disent mes documents ?"),
        intent="RAG_DOCS")

    assert resultat["status"] == "error"
    assert resultat["agent"] == "LightRAG"


async def test_lightrag_qui_repond_n_appelle_jamais_txtai(
    dossier_documents, monkeypatch,
):
    """Le chemin principal garde la main quand il fonctionne."""
    monkeypatch.setattr(routeur_chat.lightrag_tool, "query",
                        lambda *a, **k: "234 plaques, d'apres l'index.")
    monkeypatch.setattr(routeur_chat, "lightrag_echec", lambda _reponse: False)
    appels = []
    monkeypatch.setattr(routeur_chat.registre, "executer",
                        lambda *a, **k: appels.append(a) or {"statut": "SUCCESS"})

    resultat = await routeur_chat.dispatch_request(
        routeur_chat.ChatRequest(prompt="combien de plaques ?"), intent="RAG_DOCS")

    assert appels == [], "txtai a ete interroge alors que LightRAG avait repondu"
    assert resultat["agent"] == "LightRAG"
    assert resultat["status"] == "success"
