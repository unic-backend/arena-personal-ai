"""OpenViking (DEC-0058) était reachable pour `scripts/orphelins.py`
(`/api/contexte/rechercher`) mais aucune phrase d'Ousmane ne pouvait
jamais l'atteindre : le seul appelant était une route HTTP explicite que
rien, dans le chat, n'invoquait. Une capacité qui existe dans un fichier
mais que rien n'atteint depuis une conversation réelle n'est pas
intégrée — la leçon la plus chère de ce dépôt (`docs/CURRENT_TASK.md`).

Ce fichier mesure la chaîne réelle : phrase → CHAT ordinaire → registre →
`openviking.contexte`. Le connecteur lui-même est déjà testé dans
`tests/core/test_connecteur_openviking.py`.
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import chat as chat_module
from apps.backend.routers.chat import _contexte_openviking
from core.actions.resultat import echec, non_configure, succes

CLE_DE_TEST = "cle-de-test"


class RegistreDouble:
    def __init__(self, reponse=None):
        self.appels = []
        self._reponse = reponse

    def executer(self, nom: str, capacite: str, **parametres: Any) -> Any:
        self.appels.append((nom, capacite, parametres))
        return self._reponse


class TestNeSollicitePasPourReflexe:
    def test_une_phrase_sans_signal_memoire_n_appelle_jamais_le_registre(self, monkeypatch):
        registre = RegistreDouble()
        monkeypatch.setattr(chat_module, "registre", registre)

        resultat = _contexte_openviking("quel est le prix du BA13 ?", "session-1")

        assert resultat is None
        assert registre.appels == []


class TestSignalMemoire:
    def test_appelle_openviking_avec_la_phrase_et_la_session(self, monkeypatch):
        registre = RegistreDouble(reponse=succes(
            action="contexte", cible="openviking", message="1 élément assemblé.",
            preuve="1 élément(s)", entrees=[{"texte": "x"}],
            rendu="le client avait déjà refusé un devis en 2025"))
        monkeypatch.setattr(chat_module, "registre", registre)

        resultat = _contexte_openviking("on avait déjà résolu ce genre de cas ?", "session-42")

        assert registre.appels == [
            ("openviking", "contexte",
             {"requete": "on avait déjà résolu ce genre de cas ?", "session_id": "session-42"})]
        assert resultat is not None
        assert "le client avait déjà refusé un devis en 2025" in resultat

    def test_non_configure_est_omis_silencieusement(self, monkeypatch):
        registre = RegistreDouble(reponse=non_configure(
            action="contexte", cible="openviking", ce_qui_manque="OPENVIKING_URL"))
        monkeypatch.setattr(chat_module, "registre", registre)

        resultat = _contexte_openviking("on avait déjà réglé ça la dernière fois", "session-1")

        assert resultat is None

    def test_panne_est_omise_silencieusement_jamais_une_exception(self, monkeypatch):
        registre = RegistreDouble(reponse=echec(
            action="contexte", cible="openviking", message="serveur injoignable"))
        monkeypatch.setattr(chat_module, "registre", registre)

        resultat = _contexte_openviking("on avait déjà réglé ça la dernière fois", "session-1")

        assert resultat is None

    def test_succes_sans_rendu_est_omis(self, monkeypatch):
        """Un succès qui ne rend rien d'exploitable n'est pas un contexte."""
        registre = RegistreDouble(reponse=succes(
            action="contexte", cible="openviking", message="0 élément assemblé.",
            preuve="0 élément(s)", entrees=[], rendu=""))
        monkeypatch.setattr(chat_module, "registre", registre)

        resultat = _contexte_openviking("on avait déjà réglé ça la dernière fois", "session-1")

        assert resultat is None


class TestLeVraiFluxDeConversationLInjecte:
    """La chaîne complète : `/api/chat/stream`, jamais seulement la fonction
    isolée — même discipline que `TestUnFluxNeMeurtPasEnSilence` dans
    `test_api.py`, qui a trouvé le défaut jumeau (un flux qui ment sur ce
    qu'il a réellement fait)."""

    @pytest.fixture
    def client(self, monkeypatch) -> TestClient:
        monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
        return TestClient(main.app, raise_server_exceptions=False)

    @pytest.fixture
    def entetes(self) -> dict:
        return {"Authorization": f"Bearer {CLE_DE_TEST}"}

    def test_le_rendu_openviking_atteint_le_prompt_reellement_envoye(
            self, client, entetes, monkeypatch):
        registre = RegistreDouble(reponse=succes(
            action="contexte", cible="openviking", message="1 élément assemblé.",
            preuve="1 élément(s)", entrees=[{"texte": "x"}],
            rendu="SOUVENIR-DE-TEST-UNIQUE"))
        monkeypatch.setattr(chat_module, "registre", registre)

        async def conversation(*_a, **_k):
            return "CHAT"
        monkeypatch.setattr(chat_module.orchestrator, "analyze_intent", conversation)

        prompts_recus = []

        async def capture(prompt, system_prompt=None):
            prompts_recus.append(prompt)
            yield "ok"
        monkeypatch.setattr(chat_module.fast_provider, "generate_stream", capture)

        client.post("/api/chat/stream", headers=entetes,
                   json={"prompt": "on avait déjà réglé ce genre de souci ?"})

        assert registre.appels, "OpenViking n'a jamais été appelé : la capacité dort encore"
        assert prompts_recus and "SOUVENIR-DE-TEST-UNIQUE" in prompts_recus[0], (
            "le contexte OpenViking n'atteint pas le prompt réellement envoyé au modèle"
        )

    def test_une_phrase_ordinaire_n_appelle_pas_openviking(
            self, client, entetes, monkeypatch):
        registre = RegistreDouble()
        monkeypatch.setattr(chat_module, "registre", registre)

        async def conversation(*_a, **_k):
            return "CHAT"
        monkeypatch.setattr(chat_module.orchestrator, "analyze_intent", conversation)

        async def capture(prompt, system_prompt=None):
            yield "ok"
        monkeypatch.setattr(chat_module.fast_provider, "generate_stream", capture)

        client.post("/api/chat/stream", headers=entetes,
                   json={"prompt": "quel est le prix du BA13 ?"})

        assert registre.appels == []
