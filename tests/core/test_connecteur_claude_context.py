"""Claude Context : recherche sémantique de code, jamais devinée ni

exécutée sans les trois réglages requis. Même patron de double que
`tests/core/test_connecteur_opentakeoff.py` — `ClientMcpStdio` est
remplacé par une classe scriptée, aucun `npx` ni Milvus réel n'est lancé
ici (fait à la main contre le vrai serveur, pas en CI).
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

import core.connectors.claude_context as cc_mod
from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.claude_context import ConnecteurClaudeContext
from core.mcp.transport import Reponse

OUTILS = {"tools": [{"name": "index_codebase"}, {"name": "search_code"},
                    {"name": "clear_index"}, {"name": "get_indexing_status"}]}


def _echec_outil(message: str) -> Dict[str, Any]:
    return {"isError": True, "content": [{"type": "text", "text": message}]}


def fabriquer_faux_client(script: Dict[str, Any], appels: List[tuple],
                          environnements: List[Optional[Dict[str, str]]]):
    class FauxClientMcpStdio:
        def __init__(self, commande, dossier, delai=None, environnement=None):
            self.commande, self.dossier = commande, dossier
            environnements.append(environnement)

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def outils(self) -> Reponse:
            return Reponse(ok=True, resultat=OUTILS)

        def appeler(self, nom: str, arguments: Optional[Dict[str, Any]] = None) -> Reponse:
            appels.append((nom, dict(arguments or {})))
            fabrique = script.get(nom)
            if fabrique is None:
                return Reponse(ok=True, resultat=_echec_outil(f"outil {nom} non scripté pour ce test"))
            return fabrique(arguments) if callable(fabrique) else fabrique

    return FauxClientMcpStdio


def _brancher(monkeypatch, script: Dict[str, Any]):
    appels: List[tuple] = []
    environnements: List[Optional[Dict[str, str]]] = []
    monkeypatch.setattr(cc_mod, "ClientMcpStdio",
                        fabriquer_faux_client(script, appels, environnements))
    return appels, environnements


def _configure(monkeypatch, milvus="http://127.0.0.1:19530", modele="nomic-embed-text"):
    monkeypatch.setenv("CLAUDE_CONTEXT_MILVUS_ADDRESS", milvus)
    monkeypatch.setenv("CLAUDE_CONTEXT_EMBEDDING_MODEL", modele)


@pytest.fixture
def dossier_reel(tmp_path: Path) -> str:
    return str(tmp_path)


class TestNonConfigure:
    def test_sans_milvus_ni_modele_reste_non_configure(self, monkeypatch, dossier_reel):
        monkeypatch.delenv("CLAUDE_CONTEXT_MILVUS_ADDRESS", raising=False)
        monkeypatch.delenv("CLAUDE_CONTEXT_EMBEDDING_MODEL", raising=False)
        connecteur = ConnecteurClaudeContext()

        resultat = connecteur.executer("rechercher", chemin=dossier_reel, requete="authentification")

        assert resultat.statut is Statut.NON_CONFIGURE
        assert "MILVUS_ADDRESS" in resultat.message or "EMBEDDING_MODEL" in resultat.message

    def test_milvus_seul_sans_modele_reste_non_configure(self, monkeypatch, dossier_reel):
        monkeypatch.setenv("CLAUDE_CONTEXT_MILVUS_ADDRESS", "http://127.0.0.1:19530")
        monkeypatch.delenv("CLAUDE_CONTEXT_EMBEDDING_MODEL", raising=False)
        connecteur = ConnecteurClaudeContext()

        assert connecteur.sonder().etat is EtatSante.NON_CONFIGURE


class TestSante:
    def test_un_serveur_complet_est_operationnel(self, monkeypatch, dossier_reel):
        _configure(monkeypatch)
        _brancher(monkeypatch, {})
        connecteur = ConnecteurClaudeContext()

        sante = connecteur.sonder()

        assert sante.etat is EtatSante.OPERATIONNEL

    def test_un_serveur_sans_search_code_est_en_panne(self, monkeypatch, dossier_reel):
        _configure(monkeypatch)
        appels, environnements = _brancher(monkeypatch, {})

        class FauxSansOutil:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def outils(self):
                return Reponse(ok=True, resultat={"tools": [{"name": "autre_chose"}]})

        monkeypatch.setattr(cc_mod, "ClientMcpStdio", FauxSansOutil)
        connecteur = ConnecteurClaudeContext()

        assert connecteur.sonder().etat is EtatSante.EN_PANNE


class TestGardeLocalFirst:
    """La garde structurelle du module : EMBEDDING_PROVIDER est toujours
    écrasé à "Ollama", quoi que porte l'environnement hérité."""

    def test_embedding_provider_est_toujours_ollama(self, monkeypatch, dossier_reel):
        _configure(monkeypatch)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-un-vrai-secret-ailleurs-sur-la-machine")
        appels, environnements = _brancher(monkeypatch, {
            "index_codebase": Reponse(ok=True, resultat={"structuredContent": {"status": "started"}}),
        })
        connecteur = ConnecteurClaudeContext()

        connecteur.executer_confirmee("indexer", chemin=dossier_reel)

        assert environnements, "aucun processus n'a été lancé"
        assert environnements[-1]["EMBEDDING_PROVIDER"] == "Ollama"
        assert environnements[-1]["MILVUS_ADDRESS"] == "http://127.0.0.1:19530"


class TestRecherche:
    def test_recherche_reelle_rend_les_resultats(self, monkeypatch, dossier_reel):
        _configure(monkeypatch)
        resultats_bruts = [{"path": "core/permissions/controle.py", "score": 0.9,
                            "snippet": "def verifier(...):"}]
        appels, _ = _brancher(monkeypatch, {
            "search_code": Reponse(ok=True, resultat={"structuredContent": resultats_bruts}),
        })
        connecteur = ConnecteurClaudeContext()

        resultat = connecteur.executer(
            "rechercher", chemin=dossier_reel, requete="où est le contrôle de permission ?")

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["resultats"] == resultats_bruts
        assert appels[0] == ("search_code", {"path": dossier_reel, "query": "où est le contrôle de permission ?"})

    def test_recherche_sans_index_est_non_configure_pas_un_echec_muet(self, monkeypatch, dossier_reel):
        _configure(monkeypatch)
        _brancher(monkeypatch, {
            "search_code": Reponse(ok=True, resultat=_echec_outil(
                "Codebase not indexed. Please index it first.")),
        })
        connecteur = ConnecteurClaudeContext()

        resultat = connecteur.executer("rechercher", chemin=dossier_reel, requete="x")

        assert resultat.statut is Statut.NON_CONFIGURE

    def test_recherche_sans_question_n_atteint_pas_le_serveur(self, monkeypatch, dossier_reel):
        _configure(monkeypatch)
        appels, _ = _brancher(monkeypatch, {})
        connecteur = ConnecteurClaudeContext()

        resultat = connecteur.executer("rechercher", chemin=dossier_reel)

        assert resultat.statut is Statut.ECHEC
        assert appels == []

    def test_un_chemin_relatif_est_refuse(self, monkeypatch):
        _configure(monkeypatch)
        appels, _ = _brancher(monkeypatch, {})
        connecteur = ConnecteurClaudeContext()

        resultat = connecteur.executer("rechercher", chemin="core/permissions", requete="x")

        assert resultat.statut is Statut.ECHEC
        assert appels == []

    def test_un_dossier_absent_est_refuse(self, monkeypatch):
        _configure(monkeypatch)
        appels, _ = _brancher(monkeypatch, {})
        connecteur = ConnecteurClaudeContext()

        resultat = connecteur.executer("rechercher", chemin="/chemin/absolu/qui/n/existe/pas", requete="x")

        assert resultat.statut is Statut.ECHEC
        assert appels == []


class TestIndexerEtVider:
    def test_indexer_ne_demande_pas_de_confirmation(self, monkeypatch, dossier_reel):
        """`ALLOWED` sous `WRITE_FILES`, comme `graphify.construire` : un
        index local et rebâtissable ne bloque pas sur une confirmation."""
        _configure(monkeypatch)
        appels, _ = _brancher(monkeypatch, {
            "index_codebase": Reponse(ok=True, resultat={"structuredContent": {"status": "started"}}),
        })
        connecteur = ConnecteurClaudeContext()

        resultat = connecteur.executer("indexer", chemin=dossier_reel)

        assert resultat.statut is Statut.SUCCES
        assert appels[0][0] == "index_codebase"

    def test_vider_index_rend_un_succes_reel(self, monkeypatch, dossier_reel):
        _configure(monkeypatch)
        appels, _ = _brancher(monkeypatch, {
            "clear_index": Reponse(ok=True, resultat={"structuredContent": {}}),
        })
        connecteur = ConnecteurClaudeContext()

        resultat = connecteur.executer("vider_index", chemin=dossier_reel)

        assert resultat.statut is Statut.SUCCES
        assert appels[0] == ("clear_index", {"path": dossier_reel})


class TestCapacites:
    def test_aucune_capacite_de_lecture_n_ecrit(self):
        capacites = ConnecteurClaudeContext().capacites()

        assert capacites["rechercher"].ecriture is False
        assert capacites["etat_indexation"].ecriture is False
        assert capacites["indexer"].ecriture is True
        assert capacites["vider_index"].ecriture is True
