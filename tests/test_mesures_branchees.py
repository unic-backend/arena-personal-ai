"""Ce qu'une réponse a réellement coûté, face à ce que sa voie promettait.

`core/execution/mesures.py` a ses propres tests
(`tests/core/test_mesures_execution.py`). Ce fichier tient le **branchement** :
un vrai tour de chat entre au rapport avec sa durée chronométrée, un tour
interrompu n'y entre pas avec une durée, et `/api/observability` montre aussi
ce qui n'a **pas** été mesuré.

Aucun test ici n'appelle Ollama : le fournisseur est un double.
"""
import json

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import pwa_gateway
from core.execution.mesures import (
    ETAT_INDISPONIBLE,
    ETAT_MESURE,
    VERDICT_NON_MESURE,
)
from core.execution.voies import ORDRE, Voie, budget_de

CLE = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE}"}


class FauxFournisseur:
    model_name = "qwen-test"

    def __init__(self, leve=False):
        self.leve = leve

    async def is_available(self):
        return True

    async def generate_stream(self, prompt, system_prompt=None):
        if self.leve:
            raise ConnectionError("le modele a coupe")
        for morceau in ["Bon", "jour"]:
            yield morceau

    async def generate(self, prompt, system_prompt=None):
        return "Bonjour"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def rapport_neuf(monkeypatch):
    """Un rapport vide par test : les mesures d'un test ne fuitent pas dans l'autre."""
    from core.execution.mesures import Rapport

    neuf = Rapport()
    monkeypatch.setattr(pwa_gateway, "mesures_execution", neuf)
    monkeypatch.setattr("apps.backend.routers.actions.mesures_execution", neuf)
    return neuf


@pytest.fixture
def fournisseur(monkeypatch):
    def _installer(leve=False):
        faux = FauxFournisseur(leve=leve)
        monkeypatch.setattr(pwa_gateway, "fast_provider", faux)
        return faux
    return _installer


@pytest.fixture
def intention(monkeypatch):
    def _fixer(valeur):
        async def _classer(_demande):
            return valeur
        monkeypatch.setattr(pwa_gateway.orchestrator, "analyze_intent", _classer)
    return _fixer


def demander(client, text="Bonjour"):
    return client.post("/agent/stream", headers=ENTETES, json={"text": text})


# --- Un tour reel entre au rapport, avec sa duree ----------------------------------

def test_un_tour_de_chat_est_chronometre(client, fournisseur, intention, rapport_neuf):
    fournisseur()
    intention("CHAT")

    demander(client)

    assert len(rapport_neuf.mesures) == 1
    mesure = rapport_neuf.mesures[0]
    assert mesure.etat == ETAT_MESURE
    assert mesure.secondes is not None and mesure.secondes >= 0.0
    assert mesure.voie is Voie.LEGERE


def test_la_duree_est_confrontee_a_la_cible_de_la_voie(client, fournisseur, intention,
                                                       rapport_neuf):
    """Un tour doublé sans modèle tient largement la cible de 8 s de la voie légère."""
    fournisseur()
    intention("CHAT")

    demander(client)

    mesure = rapport_neuf.mesures[0]
    assert mesure.verdict == "DANS_LE_BUDGET"
    assert mesure.secondes <= budget_de(Voie.LEGERE).objectif_secondes


def test_un_agent_specialise_est_chronometre_sur_sa_propre_voie(
        client, fournisseur, intention, rapport_neuf, monkeypatch):
    fournisseur()
    intention("VIDEO_ANALYSIS")

    async def _repondre(requete, intent=None):
        return {"response": "ok", "agent": "VideoAnalyzerAgent", "intent": intent}

    monkeypatch.setattr(pwa_gateway, "dispatch_request", _repondre)

    demander(client, "analyse cette vidéo")

    mesure = rapport_neuf.mesures[0]
    assert mesure.voie is Voie.PROFONDE
    assert mesure.etat == ETAT_MESURE


# --- Ce qui n'a pas tourne n'a pas de duree ---------------------------------------

def test_un_tour_interrompu_n_entre_pas_avec_une_duree(client, fournisseur, intention,
                                                       rapport_neuf):
    """Les secondes écoulées mesureraient l'échec, pas la réponse."""
    fournisseur(leve=True)
    intention("CHAT")

    demander(client)

    assert len(rapport_neuf.mesures) == 1
    mesure = rapport_neuf.mesures[0]
    assert mesure.etat == ETAT_INDISPONIBLE
    assert mesure.secondes is None
    assert mesure.verdict == VERDICT_NON_MESURE
    assert "ConnectionError" in mesure.detail


def test_le_rapport_ne_grossit_pas_sans_fin(rapport_neuf, monkeypatch):
    from core.execution.mesures import Mesure

    monkeypatch.setattr(pwa_gateway, "MESURES_GARDEES", 3)
    for numero in range(10):
        pwa_gateway.noter_mesure(Mesure(nom=f"tour {numero}", voie=Voie.LEGERE,
                                        etat=ETAT_MESURE, secondes=0.1))

    assert len(rapport_neuf.mesures) == 3
    assert [m.nom for m in rapport_neuf.mesures] == ["tour 7", "tour 8", "tour 9"]


# --- La route montre aussi ce qui manque ------------------------------------------

def lire_mesures(client):
    reponse = client.get("/api/observability", headers=ENTETES)
    assert reponse.status_code == 200
    return reponse.json()


def test_les_voies_jamais_empruntees_restent_au_tableau(client, rapport_neuf):
    """Sans elles, le tableau ne montrerait que ce qui a marché."""
    corps = lire_mesures(client)

    voies_citees = {ligne["voie"] for ligne in corps["mesures"]}
    assert voies_citees == {voie.value for voie in ORDRE}
    assert corps["resume"]["unknown"] == len(ORDRE)
    assert corps["resume"]["mesurees"] == 0


def test_une_absence_de_mesure_n_est_pas_zero(client, rapport_neuf):
    corps = lire_mesures(client)

    assert all(ligne["secondes"] is None for ligne in corps["mesures"])
    assert corps["resume"]["mediane_secondes"] is None
    assert "UNKNOWN" in corps["tableau"]


def test_une_absence_de_mesure_n_est_ni_tenue_ni_manquee(client, rapport_neuf):
    corps = lire_mesures(client)

    assert all(ligne["verdict"] == VERDICT_NON_MESURE for ligne in corps["mesures"])
    assert corps["resume"]["hors_budget"] == 0


def test_le_tour_mesure_apparait_dans_la_route(client, fournisseur, intention,
                                               rapport_neuf):
    fournisseur()
    intention("CHAT")
    demander(client)

    corps = lire_mesures(client)

    mesurees = [ligne for ligne in corps["mesures"] if ligne["etat"] == ETAT_MESURE]
    assert len(mesurees) == 1
    assert mesurees[0]["cible_secondes"] == budget_de(Voie.LEGERE).objectif_secondes
    assert corps["resume"]["mediane_secondes"] is not None
    # La voie legere a servi : elle n'est plus annoncee comme jamais empruntee.
    assert corps["resume"]["unknown"] == len(ORDRE) - 1


def test_la_route_exige_la_cle(client):
    assert client.get("/api/observability").status_code in (401, 403)


def test_les_cibles_annoncees_sont_celles_des_voies(client, rapport_neuf):
    corps = lire_mesures(client)

    assert corps["cibles"] == {
        voie.value: budget_de(voie).objectif_secondes for voie in ORDRE}
    assert json.dumps(corps), "la reponse doit rester serialisable"
