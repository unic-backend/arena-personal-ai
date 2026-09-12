"""`galsen` reveille : la donnee officielle du Senegal avant le web.

Un des cinq connecteurs qu'aucun chemin n'atteignait — sa raison etait
« aucune intention ne les convoque » alors qu'il etait, lui, OPERATIONNEL
(API publique, sans cle). Reveille le 12/09/2026, a la demande du
proprietaire, sur l'intention qui pose exactement ce genre de question.

Ce que ces tests refusent : qu'une question ordinaire soit detournee vers
l'API, et qu'une API muette empeche la recherche web de repondre.
"""
import pytest

from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import question_de_donnee_senegalaise


class TestQuandLaQuestionEnReleve:
    @pytest.mark.parametrize("question", [
        "combien d'habitants a Ziguinchor ?",
        "quelle est la population de la region de Thies ?",
        "superficie du departement de Mbour au Senegal",
        "liste les communes de Kaolack",
    ])
    def test_une_question_administrative_est_reconnue(self, question):
        assert question_de_donnee_senegalaise(question) is True

    @pytest.mark.parametrize("question", [
        "quelle est la derniere version de FastAPI ?",
        "qui a gagne le match hier ?",
        "fais-moi un devis pour 18 metres de cloison",
        "quelle est la population mondiale ?",
        "il y a du monde a Dakar ce soir ?",
    ])
    def test_une_question_ordinaire_n_est_jamais_detournee(self, question):
        assert question_de_donnee_senegalaise(question) is False


class TestSurLeVraiChemin:
    async def test_la_donnee_officielle_passe_avant_la_recherche_web(self, monkeypatch):
        recus = {}

        def _executer(nom, capacite, **parametres):
            recus["appel"] = (nom, capacite)
            recus["q"] = parametres.get("q")
            return {"statut": "SUCCESS",
                    "message": "Ziguinchor : 549 151 habitants (ANSD).",
                    "detail": {"source": "ANSD"}}
        monkeypatch.setattr(routeur_chat.registre, "executer", _executer)

        web = []

        async def _web(prompt, context=None):
            web.append(prompt)
            return {"response": "d'apres un blog...", "agent": "FreshInfoAgent"}
        monkeypatch.setattr(routeur_chat.fresh_agent, "run", _web)

        resultat = await routeur_chat.dispatch_request(
            routeur_chat.ChatRequest(prompt="combien d'habitants a Ziguinchor ?"),
            intent="FRESH_INFO")

        assert recus.get("appel") == ("galsen", "rechercher"), (
            f"l'API officielle n'a pas ete interrogee : {recus}")
        assert web == [], "la recherche web a tourne alors que la donnee officielle existait"
        assert resultat["agent"] == "GalsenAPI"
        assert "549 151" in resultat["response"]
        assert resultat["status"] == "success"

    async def test_une_api_muette_laisse_le_web_repondre(self, monkeypatch):
        """Une donnee officielle absente ne doit pas priver de reponse."""
        monkeypatch.setattr(routeur_chat.registre, "executer",
                            lambda *a, **k: {"statut": "ECHEC",
                                             "message": "API injoignable."})
        web = []

        async def _web(prompt, context=None):
            web.append(prompt)
            return {"response": "reponse du web", "agent": "FreshInfoAgent"}
        monkeypatch.setattr(routeur_chat.fresh_agent, "run", _web)

        resultat = await routeur_chat.dispatch_request(
            routeur_chat.ChatRequest(prompt="population de la region de Thies ?"),
            intent="FRESH_INFO")

        assert web, "le repli web n'a pas eu lieu"
        assert resultat["agent"] == "FreshInfoAgent"

    async def test_une_question_ordinaire_n_appelle_jamais_l_api(self, monkeypatch):
        appels = []
        monkeypatch.setattr(routeur_chat.registre, "executer",
                            lambda *a, **k: appels.append(a) or {"statut": "SUCCESS"})

        async def _web(prompt, context=None):
            return {"response": "ok", "agent": "FreshInfoAgent"}
        monkeypatch.setattr(routeur_chat.fresh_agent, "run", _web)

        await routeur_chat.dispatch_request(
            routeur_chat.ChatRequest(prompt="quelle est la derniere version de FastAPI ?"),
            intent="FRESH_INFO")

        assert appels == [], f"une question ordinaire est partie vers galsen : {appels}"
