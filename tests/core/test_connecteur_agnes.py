"""Connecteur Agnes — generation video, service auto-heberge separe.

**Le trou mesure le 23/09/2026, et ce que ce fichier couvre.**
`tools.video.AgnesProductionBridge` existait deja avec vingt fichiers de
tests, mais aucun connecteur ne le rattachait au registre : ni la
confirmation (`video_generation.generate = CONFIRMATION`,
`config/permissions_services.yaml`), ni la sonde honnete, ni le contrat
`{done, result: {success, generated_files}}` que
`core/connectors/suivi_video.py::suivre_generation` sait deja suivre. Ce
fichier verifie CE connecteur, pas le pont HTTP lui-meme (deja couvert par
`tests/tools/test_agnes_video_provider.py` et voisins) — la couche reseau
est toujours injectee, jamais appelee.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from core.actions.resultat import Statut
from core.connectors.agnes import GENERATIONS_PAR_MINUTE, AgnesConnector
from core.connectors.base import EtatSante


class FausseBridge:
    """Simule `AgnesProductionBridge` sans reseau reel."""

    def __init__(
        self,
        disponible: bool = True,
        soumission: Optional[Dict[str, Any]] = None,
        etat: Optional[Dict[str, Any]] = None,
        collecte: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.disponible = disponible
        self.appels_submit = []
        self.appels_status = []
        self.appels_collect = []
        self.appels_stop = []
        self._soumission = soumission
        self._etat = etat
        self._collecte = collecte
        self.orchestrator = self  # pour orchestrator.agnes.stop(...)
        self.agnes = self  # meme objet : suffisant pour le test d'annulation

    def health(self) -> Dict[str, Any]:
        if self.disponible:
            return {"available": True, "provider": "agnes"}
        return {"available": False, "provider": "agnes", "reason": "connexion refusee"}

    def submit(self, prompt: str, *, workflow: str = "simple", **options: Any) -> Dict[str, Any]:
        self.appels_submit.append({"prompt": prompt, "workflow": workflow, **options})
        return self._soumission or {
            "statut": "SUBMITTED", "message": f"Agnes: tache abc123 {workflow}.",
            "task_id": "abc123", "provider": "agnes", "workflow": workflow,
            "etat_provider": "created",
        }

    def status(self, task_id: str) -> Dict[str, Any]:
        self.appels_status.append(task_id)
        return self._etat or {
            "statut": "SUCCESS", "task_id": task_id, "provider": "agnes",
            "workflow": "status", "etat_provider": "processing",
        }

    def collect(self, task_id: str, *, filename: Optional[str] = None) -> Dict[str, Any]:
        self.appels_collect.append(task_id)
        return self._collecte or {
            "statut": "SUCCESS", "message": "Agnes: video terminee et collectee par ARENA.",
            "task_id": task_id, "provider": "agnes",
            "preuve": f"/rendered/agnes-{task_id}.mp4",
        }

    def stop(self, task_id: str) -> Dict[str, Any]:
        self.appels_stop.append(task_id)
        return {"stopped": True}


@pytest.fixture
def connecteur() -> AgnesConnector:
    return AgnesConnector(bridge=FausseBridge())


# --- generer : soumission derriere confirmation ------------------------------

def test_une_generation_ne_part_jamais_sans_confirmation(connecteur):
    resultat = connecteur.executer("generer", prompt="un chat qui saute")

    assert resultat.statut is Statut.A_CONFIRMER
    assert not resultat.a_eu_lieu
    assert connecteur._bridge.appels_submit == []


def test_la_generation_confirmee_envoie_le_prompt_et_le_workflow(connecteur):
    resultat = connecteur.executer_confirmee(
        "generer", prompt="un chat cyberpunk", workflow="creative", duration=8)

    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve == "abc123"
    appel = connecteur._bridge.appels_submit[0]
    assert appel["prompt"] == "un chat cyberpunk"
    assert appel["workflow"] == "creative"
    assert appel["duration"] == 8


def test_une_generation_sans_prompt_ne_part_pas(connecteur):
    resultat = connecteur.executer_confirmee("generer", prompt="")

    assert resultat.statut is Statut.ECHEC
    assert connecteur._bridge.appels_submit == []


def test_une_generation_sans_identifiant_rendu_n_est_pas_prouvee():
    bridge = FausseBridge(soumission={"statut": "SUBMITTED", "message": "ok"})
    connecteur = AgnesConnector(bridge=bridge)

    resultat = connecteur.executer_confirmee("generer", prompt="un chat")

    assert resultat.statut is Statut.ECHEC
    assert "identifiant" in resultat.message


def test_un_agnes_indisponible_est_non_configure_jamais_un_echec_muet():
    bridge = FausseBridge(soumission={
        "statut": "ERROR", "message": "Agnes unavailable: [Errno 111] Connection refused"})
    connecteur = AgnesConnector(bridge=bridge)

    resultat = connecteur.executer_confirmee("generer", prompt="un chat")

    assert resultat.statut is Statut.NON_CONFIGURE


def test_un_refus_du_provider_est_un_echec_avec_sa_raison():
    bridge = FausseBridge(soumission={"statut": "ERROR", "message": "prompt rejete par le filtre"})
    connecteur = AgnesConnector(bridge=bridge)

    resultat = connecteur.executer_confirmee("generer", prompt="un chat")

    assert resultat.statut is Statut.ECHEC
    assert "filtre" in resultat.message


# --- etat_travail : termine n'est jamais pris pour une preuve ---------------

def test_une_tache_en_cours_n_est_pas_terminee():
    bridge = FausseBridge(etat={"etat_provider": "processing"})
    connecteur = AgnesConnector(bridge=bridge)

    resultat = connecteur.executer("etat_travail", job_id="abc123")

    assert resultat.statut is Statut.SUCCES
    assert resultat.detail["donnees"]["done"] is False
    assert bridge.appels_collect == [], "une tache en cours ne doit jamais etre collectee"


def test_une_tache_terminee_est_collectee_avant_de_confirmer_le_succes():
    bridge = FausseBridge(etat={"etat_provider": "completed"})
    connecteur = AgnesConnector(bridge=bridge)

    resultat = connecteur.executer("etat_travail", job_id="abc123")

    assert bridge.appels_collect == ["abc123"], "termine n'est jamais pris pour une preuve"
    instantane = resultat.detail["donnees"]
    assert instantane["done"] is True
    assert instantane["result"]["success"] is True
    assert instantane["result"]["generated_files"] == ["/rendered/agnes-abc123.mp4"]


def test_une_collecte_qui_echoue_ne_rend_pas_un_succes():
    bridge = FausseBridge(
        etat={"etat_provider": "completed"},
        collecte={"statut": "ERROR", "message": "fichier introuvable cote provider"})
    connecteur = AgnesConnector(bridge=bridge)

    resultat = connecteur.executer("etat_travail", job_id="abc123")

    instantane = resultat.detail["donnees"]
    assert instantane["done"] is True
    assert instantane["result"]["success"] is False
    assert instantane["result"]["generated_files"] == []
    assert "fichier introuvable" in instantane["result"]["errors"][0]


def test_l_etat_sans_identifiant_ne_regarde_rien(connecteur):
    resultat = connecteur.executer("etat_travail", job_id="  ")

    assert resultat.statut is Statut.ECHEC
    assert "Aucun identifiant" in resultat.message
    assert connecteur._bridge.appels_status == []


# --- annuler : une annulation reelle, pas un succes invente -----------------

def test_annuler_appelle_reellement_le_provider(connecteur):
    resultat = connecteur.executer_confirmee("annuler_travail", job_id="abc123")

    assert resultat.statut is Statut.SUCCES
    assert connecteur._bridge.appels_stop == ["abc123"]


def test_annuler_sans_identifiant_ne_regarde_rien(connecteur):
    resultat = connecteur.executer_confirmee("annuler_travail", job_id="")

    assert resultat.statut is Statut.ECHEC
    assert connecteur._bridge.appels_stop == []


# --- Sante ---------------------------------------------------------------------

def test_agnes_joignable_est_operationnel(connecteur):
    assert connecteur.sonder().etat is EtatSante.OPERATIONNEL


def test_agnes_injoignable_est_non_configure():
    connecteur = AgnesConnector(bridge=FausseBridge(disponible=False))

    sante = connecteur.sonder()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "connexion refusee" in sante.message


# --- Capacites declarees -----------------------------------------------------------

def test_les_capacites_declarees(connecteur):
    capacites = connecteur.capacites()

    assert set(capacites) == {"generer", "etat_travail", "annuler_travail"}
    assert [nom for nom, c in capacites.items() if c.ecriture] == ["generer", "annuler_travail"]
    assert capacites["generer"].quota_par_minute == GENERATIONS_PAR_MINUTE


def test_le_service_declare_est_video_generation(connecteur):
    """Meme service que wangp/moneyprinter/xaar_kaname : une generation
    video reste une generation video, jamais une deuxieme regle de
    permission a maintenir en double."""
    assert connecteur.service == "video_generation"


def test_la_regle_exige_bien_une_confirmation():
    """La protection est dans un fichier de configuration : un test la
    mesure, sinon elle se fait retirer sans que rien ne tombe."""
    from pathlib import Path

    import yaml
    racine = Path(__file__).resolve().parents[2]
    regles = yaml.safe_load(
        (racine / "config" / "permissions_services.yaml").read_text(encoding="utf-8"))

    assert regles["services"]["video_generation"]["generate"]["decision"] == "CONFIRMATION"
    assert regles["services"]["video_generation"]["cancel"]["decision"] == "ALLOWED"


@pytest.mark.parametrize("interdite", ["supprimer", "delete", "pipeline"])
def test_capacite_hors_liste_n_existe_pas(connecteur, interdite):
    assert connecteur.executer(interdite).statut is Statut.NON_IMPLEMENTE


# --- Le VRAI branchement, pas une chaine cherchee dans le source ------------
#
# Mesure du 23/09/2026 : les tests de "reachabilite" ajoutes autour de ce
# trou (PR #288/#289/#290) cherchaient des sous-chaines deja presentes AVANT
# Agnes dans les fichiers source (`'elif intent == "VIDEO_PROJET"'`,
# `"video_production_agent.run("`...) — aucun n'importait le vrai module ni
# n'appelait le vrai registre. Ce test importe `apps.backend.runtime` pour de
# vrai et verifie les objets reellement construits au demarrage du serveur.
# Une regression qui retirerait la ligne `registre.declarer("agnes", ...)`
# ferait tomber CE test ; un test sur une chaine de caracteres ne l'aurait
# jamais vue.

def test_le_registre_reel_du_serveur_declare_agnes():
    from apps.backend.runtime import registre

    assert registre.est_declare("agnes")
    instance = registre.obtenir("agnes")
    assert instance.service == "video_generation"
    assert instance.nom == "agnes"


def test_l_agent_video_reel_du_serveur_partage_ce_meme_registre():
    from apps.backend.runtime import registre, video_production_agent

    assert video_production_agent.registre is registre
