"""Drift (DEC-0057) : un éditeur vidéo GPLv3, appelé par son propre serveur
MCP — jamais importé, jamais confondu avec le workspace métier UniC
Plaquiste.

Même patron que `tests/core/test_connecteur_wan2gp.py` : un `FauxClient` MCP
qui note ce qu'on lui demande, sans réseau. Deux tests structurants en plus
de ceux de WanGP : le jeton Bearer voyage réellement dans l'en-tête (c'est
la seule chose que ce connecteur ajoute au transport), et la frontière du
workspace Video est tenue par grep, pas par promesse.
"""
from pathlib import Path
from typing import Any, Dict, Optional

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.drift import ConnecteurDrift
from core.mcp.transport import ClientMcp, Reponse

OUTILS = {"tools": [{"name": "catalog"}, {"name": "toolbox"}, {"name": "apply"},
                    {"name": "inspect"}, {"name": "capture"}]}

RACINE = Path(__file__).resolve().parents[2]


class FauxClient:
    """Un serveur MCP Drift de test : il note ce qu'on lui demande."""

    def __init__(self, outils: Optional[Dict[str, Any]] = None,
                 reponses: Optional[Dict[str, Any]] = None, panne: str = "") -> None:
        self.url = "http://faux/mcp"
        self._outils = outils if outils is not None else OUTILS
        self._reponses = reponses or {}
        self._panne = panne
        self.appels = []

    def outils(self) -> Reponse:
        if self._panne:
            return Reponse(ok=False, raison=self._panne)
        return Reponse(ok=True, resultat=self._outils)

    def appeler(self, nom: str, arguments: Optional[Dict[str, Any]] = None) -> Reponse:
        self.appels.append((nom, dict(arguments or {})))
        if self._panne:
            return Reponse(ok=False, raison=self._panne)
        return Reponse(ok=True, resultat={
            "structuredContent": self._reponses.get(nom, {"ok": True})})


def connecteur(**kwargs) -> ConnecteurDrift:
    return ConnecteurDrift(client=FauxClient(**kwargs))


# --- La confirmation, comme WanGP -------------------------------------------------

def test_appliquer_ne_part_jamais_sans_confirmation():
    faux = FauxClient()
    drift = ConnecteurDrift(client=faux)

    resultat = drift.executer("appliquer", ops=[{"toolbox": "timeline", "op": "split_on_beats"}])

    assert resultat.statut is not Statut.SUCCES
    assert faux.appels == [], "l'appel a atteint Drift sans confirmation"


def test_une_liste_d_operations_confirmee_atteint_drift():
    faux = FauxClient()
    drift = ConnecteurDrift(client=faux)

    resultat = drift.executer_confirmee(
        "appliquer", ops=[{"toolbox": "timeline", "op": "split_on_beats", "params": {}}])

    assert resultat.statut is Statut.SUCCES
    assert "1 opération" in resultat.preuve
    assert faux.appels[0][0] == "apply"


def test_appliquer_sans_operations_n_atteint_pas_drift():
    faux = FauxClient()
    drift = ConnecteurDrift(client=faux)

    resultat = drift.executer_confirmee("appliquer", ops=[])

    assert resultat.statut is Statut.ECHEC
    assert faux.appels == []


def test_aucune_capacite_de_lecture_n_ecrit():
    lectures = ["catalogue", "boite_a_outils", "etat_projet", "capture"]
    capacites = connecteur().capacites()

    assert not any(capacites[nom].ecriture for nom in lectures)
    assert capacites["appliquer"].ecriture is True


# --- La sonde interroge, elle ne suppose pas ---------------------------------------

def test_sans_url_le_connecteur_dit_ce_qui_manque(monkeypatch):
    monkeypatch.delenv("DRIFT_MCP_URL", raising=False)
    monkeypatch.delenv("DRIFT_MCP_TOKEN", raising=False)
    drift = ConnecteurDrift()

    sante = drift.sante()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "Agent access" in sante.ce_qui_manque


def test_sans_jeton_le_connecteur_reste_non_configure(monkeypatch):
    monkeypatch.setenv("DRIFT_MCP_URL", "http://127.0.0.1:9999")
    monkeypatch.delenv("DRIFT_MCP_TOKEN", raising=False)
    drift = ConnecteurDrift()

    assert drift.sante().etat is EtatSante.NON_CONFIGURE


def test_un_serveur_qui_repond_sans_savoir_appliquer_est_en_panne():
    drift = connecteur(outils={"tools": [{"name": "catalog"}]})

    assert drift.sante().etat is EtatSante.EN_PANNE


def test_un_serveur_complet_est_operationnel():
    drift = connecteur()

    sante = drift.sante()

    assert sante.etat is EtatSante.OPERATIONNEL
    assert "édition disponible" in sante.message


# --- Le jeton Bearer, seule chose que ce connecteur ajoute au transport ------------

def test_le_jeton_bearer_voyage_dans_l_en_tete(monkeypatch):
    monkeypatch.setenv("DRIFT_MCP_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("DRIFT_MCP_TOKEN", "secret-de-session")
    drift = ConnecteurDrift()

    client = drift._client()

    assert isinstance(client, ClientMcp)
    assert client._entetes()["Authorization"] == "Bearer secret-de-session"


def test_sans_jeton_aucun_en_tete_authorization():
    client = ClientMcp("http://127.0.0.1:9999")

    assert "Authorization" not in client._entetes()


# --- Ce que l'appelant ne choisit pas -----------------------------------------------

def test_l_appelant_ne_choisit_pas_l_appel_mcp():
    faux = FauxClient()
    drift = ConnecteurDrift(client=faux)

    drift.executer("boite_a_outils", name="timeline", outil="rm -rf", chemin="../")

    assert faux.appels == [("toolbox", {"name": "timeline"})]


def test_une_capacite_non_declaree_n_atteint_jamais_drift():
    faux = FauxClient()
    drift = ConnecteurDrift(client=faux)

    resultat = drift.executer("supprimer_tout")

    assert resultat.statut is not Statut.SUCCES
    assert faux.appels == []


def test_boite_a_outils_sans_nom_n_atteint_pas_drift():
    faux = FauxClient()
    drift = ConnecteurDrift(client=faux)

    resultat = drift.executer("boite_a_outils")

    assert resultat.statut is Statut.ECHEC
    assert faux.appels == []


# --- La frontière du workspace Video, tenue par grep, pas par promesse ------------

class TestFrontiereWorkspaceVideo:
    """Mission du 06/09/2026 : « DRIFT APPARTIENT EXCLUSIVEMENT AU WORKSPACE
    VIDEO ». Aucun chemin plaquiste/BIM/métier ne doit référencer ce module."""

    #: Le SEUL sous-ensemble du code source (hors tests/docs) autorisé à
    #: nommer Drift. Un nouveau fichier hors de cette liste qui le
    #: référencerait ferait échouer ce test — c'est voulu : la frontière se
    #: mesure à chaque ajout, elle ne se déclare pas une fois pour toutes.
    FICHIERS_AUTORISES = {
        "core/connectors/drift.py",
        "core/production/plan_video.py",
        "core/production/plan_drift.py",
        "agents/video/production_agent.py",
        "apps/backend/runtime.py",
        "config/permissions_services.yaml",
    }

    #: Seuls ces quatre dossiers du depot forment le code source d'ARENA —
    #: le reste (`.claude/`, `tests/`, `docs/`, `scripts/`...) peut nommer
    #: le mot anglais "drift" (derive de modele, derive de config) sans
    #: rapport avec CutWire-Studios/Drift.
    DOSSIERS_SOURCE = ("core", "agents", "apps", "config")

    def test_drift_n_est_reference_que_dans_le_workspace_video(self):
        for dossier in self.DOSSIERS_SOURCE:
            for chemin in (RACINE / dossier).rglob("*"):
                if not chemin.is_file() or chemin.suffix not in (".py", ".yaml", ".yml"):
                    continue
                relatif = chemin.relative_to(RACINE).as_posix()
                if relatif in self.FICHIERS_AUTORISES:
                    continue
                if any(part in {".venv", "venv", "node_modules", "__pycache__"} for part in chemin.parts):
                    continue
                contenu = chemin.read_text(encoding="utf-8", errors="ignore")
                # Sensible a la casse : "Drift" (le logiciel) s'ecrit toujours
                # avec une majuscule dans ce depot ; "drift" en minuscule est
                # un mot anglais ordinaire (derive), sans rapport.
                assert "Drift" not in contenu, \
                    f"{relatif} référence Drift, hors de la liste autorisée."
