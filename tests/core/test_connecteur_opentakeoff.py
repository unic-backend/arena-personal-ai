"""Le connecteur OpenTakeoff : le metre reel, jamais suppose ni invente.

`ClientMcpStdio` est remplace par un double scripte — aucun test ici ne lance
Node ni le vrai moteur (ca, c'est fait a la main contre le depot reel, pas en
CI). Le double parle exactement le meme contrat : `outils()`/`appeler()`
rendent des `Reponse`, `isError` distingue un echec applicatif d'une panne de
transport — voir `core/mcp/stdio_transport.py` et le probe manuel qui a etabli
ce contrat.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

import core.connectors.opentakeoff as opentakeoff_mod
from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.opentakeoff import ConnecteurOpenTakeoff, _erreur_outil
from core.mcp.transport import Reponse


def _texte(reponse_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Une reponse d'outil reussie, avec `structuredContent`."""
    return {"structuredContent": reponse_dict, "content": []}


def _echec_outil(message: str) -> Dict[str, Any]:
    return {"isError": True, "content": [{"type": "text", "text": message}]}


def fabriquer_faux_client(script: Dict[str, Any], appels: List[tuple]):
    """Une classe qui remplace `ClientMcpStdio`, scriptee par nom d'outil.

    `script[nom]` est soit une `Reponse` directe, soit un callable
    `(arguments) -> Reponse` pour un comportement qui depend des arguments
    (ex. `load_plan` rend les feuilles du chemin demande).
    """

    class FauxClientMcpStdio:
        def __init__(self, commande, dossier, delai=None):
            self.commande, self.dossier = commande, dossier

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def outils(self) -> Reponse:
            return Reponse(ok=True, resultat={"tools": [{"name": n} for n in script]})

        def appeler(self, nom: str, arguments: Optional[Dict[str, Any]] = None) -> Reponse:
            appels.append((nom, dict(arguments or {})))
            fabrique = script.get(nom)
            if fabrique is None:
                return Reponse(ok=True, resultat=_echec_outil(f"outil {nom} non scripte pour ce test"))
            return fabrique(arguments) if callable(fabrique) else fabrique

    return FauxClientMcpStdio


@pytest.fixture
def plan_pdf(tmp_path: Path) -> str:
    """Un fichier reel — le connecteur verifie sa presence avant tout appel MCP."""
    chemin = tmp_path / "plan.pdf"
    chemin.write_bytes(b"%PDF-1.4 faux plan pour un test\n")
    return str(chemin)


def _brancher(monkeypatch, script: Dict[str, Any]) -> List[tuple]:
    # `_commande()` decide si OpenTakeoff est "construit" en regardant le
    # disque (`dist/server.js`) : le simuler configure, sans toucher a
    # `Path.is_file` — un vrai fichier PDF de test (`plan_pdf`) doit continuer
    # a se voir comme present par le MEME test.
    monkeypatch.setattr(opentakeoff_mod, "_commande", lambda: ["node", "dist/server.js"])
    appels: List[tuple] = []
    monkeypatch.setattr(opentakeoff_mod, "ClientMcpStdio", fabriquer_faux_client(script, appels))
    return appels


UNE_PIECE = {
    "detected": 1,
    "rooms": [{"label": "101", "area_sf": 100.0, "perimeter_lf": 40.0, "confidence": 1,
               "shape_id": "shp-1", "condition": opentakeoff_mod.CONDITION_SURFACE}],
}
RESUME_VIDE = {"conditions": [], "totals": {"total_sf_net": 0, "lf_net": 0}}


class TestSante:
    def test_non_configure_sans_repertoire_construit(self, monkeypatch):
        # `_commande()` lit le disque (OPENTAKEOFF_MCP_DIR + dist/server.js) —
        # module-level, comme BASE_URL dans moneyprinter.py. On simule
        # directement son verdict ("rien de construit") plutot que l'env var
        # dont il derive, deja figee a l'import.
        monkeypatch.setattr(opentakeoff_mod, "_commande", lambda: None)
        connecteur = ConnecteurOpenTakeoff()

        sante = connecteur.sonder()

        assert sante.etat == EtatSante.NON_CONFIGURE
        assert "OPENTAKEOFF_MCP_DIR" in sante.message or "dist/server.js" in sante.message

    def test_operationnel_quand_le_serveur_repond(self, monkeypatch):
        _brancher(monkeypatch, {})
        connecteur = ConnecteurOpenTakeoff()

        sante = connecteur.sonder()

        assert sante.etat == EtatSante.OPERATIONNEL


class TestMesurer:
    def test_sans_chemin_est_un_echec(self, monkeypatch):
        _brancher(monkeypatch, {})
        connecteur = ConnecteurOpenTakeoff()

        resultat = connecteur.executer("mesurer", chemin="")

        assert resultat.statut is Statut.ECHEC

    def test_fichier_absent_est_un_echec(self, monkeypatch):
        _brancher(monkeypatch, {})
        connecteur = ConnecteurOpenTakeoff()

        resultat = connecteur.executer("mesurer", chemin="/rien/ici/plan.pdf")

        assert resultat.statut is Statut.ECHEC
        assert "plan.pdf" in resultat.message

    def test_plan_illisible_est_un_echec(self, monkeypatch, plan_pdf):
        script = {"load_plan": Reponse(ok=True, resultat=_echec_outil("PDF corrompu"))}
        _brancher(monkeypatch, script)
        connecteur = ConnecteurOpenTakeoff()

        resultat = connecteur.executer("mesurer", chemin=plan_pdf)

        assert resultat.statut is Statut.ECHEC
        assert "PDF corrompu" in resultat.message

    def test_agrege_les_pieces_de_toutes_les_feuilles(self, monkeypatch, plan_pdf):
        def piece(numero):
            return _texte({"detected": 1, "rooms": [
                {"label": numero, "area_sf": 50.0, "perimeter_lf": 20.0, "confidence": 1}]})

        script = {
            "load_plan": Reponse(ok=True, resultat=_texte({
                "sheets": [{"sheet": "a.pdf#1"}, {"sheet": "a.pdf#2"}]})),
            "set_scale": Reponse(ok=True, resultat=_texte({"upp": 0.01})),
            "detect_rooms": lambda args: Reponse(
                ok=True, resultat=piece("101" if args["sheet"].endswith("1") else "201")),
            "derive_base": Reponse(ok=True, resultat=_texte({})),
            "takeoff_summary": Reponse(ok=True, resultat=_texte(
                {"totals": {"total_sf_net": 100.0, "lf_net": 80.0}})),
        }
        appels = _brancher(monkeypatch, script)
        connecteur = ConnecteurOpenTakeoff()

        resultat = connecteur.executer("mesurer", chemin=plan_pdf)

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["pieces_totales"] == 2
        assert {p["numero"] for p in resultat.detail["pieces"]} == {"101", "201"}
        assert resultat.detail["feuilles_mesurees"] == ["a.pdf#1", "a.pdf#2"]
        assert resultat.detail["feuilles_sans_echelle"] == []
        noms_appeles = [nom for nom, _ in appels]
        assert noms_appeles.count("set_scale") == 2
        assert noms_appeles.count("detect_rooms") == 2
        assert noms_appeles.count("derive_base") == 1  # une seule fois, pour toute la session
        assert noms_appeles.count("takeoff_summary") == 1

    def test_une_feuille_sans_echelle_n_arrete_pas_les_autres(self, monkeypatch, plan_pdf):
        script = {
            "load_plan": Reponse(ok=True, resultat=_texte({
                "sheets": [{"sheet": "ok.pdf"}, {"sheet": "sans-echelle.pdf"}]})),
            "set_scale": lambda args: (
                Reponse(ok=True, resultat=_texte({"upp": 0.01}))
                if args["sheet"] == "ok.pdf"
                else Reponse(ok=True, resultat=_echec_outil("Aucune echelle detectee sur ce plan."))),
            "detect_rooms": Reponse(ok=True, resultat=_texte(UNE_PIECE)),
            "derive_base": Reponse(ok=True, resultat=_texte({})),
            "takeoff_summary": Reponse(ok=True, resultat=_texte(
                {"totals": {"total_sf_net": 100.0, "lf_net": 40.0}})),
        }
        _brancher(monkeypatch, script)
        connecteur = ConnecteurOpenTakeoff()

        resultat = connecteur.executer("mesurer", chemin=plan_pdf)

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["feuilles_mesurees"] == ["ok.pdf"]
        assert resultat.detail["feuilles_sans_echelle"] == ["sans-echelle.pdf"]

    def test_aucune_feuille_exploitable_est_un_echec_nomme(self, monkeypatch, plan_pdf):
        script = {
            "load_plan": Reponse(ok=True, resultat=_texte({"sheets": [{"sheet": "x.pdf"}]})),
            "set_scale": Reponse(ok=True, resultat=_echec_outil("Aucune echelle detectee.")),
        }
        _brancher(monkeypatch, script)
        connecteur = ConnecteurOpenTakeoff()

        resultat = connecteur.executer("mesurer", chemin=plan_pdf)

        assert resultat.statut is Statut.ECHEC
        assert "x.pdf" in resultat.message


class TestExporter:
    def test_une_confirmation_est_demandee_avant_tout_ecrit(self, monkeypatch, plan_pdf):
        appels = _brancher(monkeypatch, {})
        connecteur = ConnecteurOpenTakeoff()

        resultat = connecteur.executer("exporter", chemin=plan_pdf)

        assert resultat.statut is Statut.A_CONFIRMER
        assert appels == [], "rien ne doit avoir ete appele avant la confirmation"

    def test_confirme_ecrit_le_rapport_et_le_plan_marque(self, monkeypatch, plan_pdf):
        script = {
            "load_plan": Reponse(ok=True, resultat=_texte({"sheets": [{"sheet": "a.pdf"}]})),
            "set_scale": Reponse(ok=True, resultat=_texte({"upp": 0.01})),
            "detect_rooms": Reponse(ok=True, resultat=_texte(UNE_PIECE)),
            "derive_base": Reponse(ok=True, resultat=_texte({})),
            "takeoff_summary": Reponse(ok=True, resultat=_texte(
                {"totals": {"total_sf_net": 100.0, "lf_net": 40.0}})),
            "export_report": Reponse(ok=True, resultat=_texte({"schema": "opentakeoff.report.v1"})),
            "export_marked_pdf": Reponse(ok=True, resultat=_texte({"path": "/x/plan - marked set.pdf"})),
        }
        _brancher(monkeypatch, script)
        connecteur = ConnecteurOpenTakeoff()

        resultat = connecteur.executer_confirmee("exporter", chemin=plan_pdf)

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["chemin_marque"] == "/x/plan - marked set.pdf"
        assert resultat.preuve == "/x/plan - marked set.pdf"

    def test_rapport_non_ecrit_est_un_echec(self, monkeypatch, plan_pdf):
        script = {
            "load_plan": Reponse(ok=True, resultat=_texte({"sheets": [{"sheet": "a.pdf"}]})),
            "set_scale": Reponse(ok=True, resultat=_texte({"upp": 0.01})),
            "detect_rooms": Reponse(ok=True, resultat=_texte(UNE_PIECE)),
            "derive_base": Reponse(ok=True, resultat=_texte({})),
            "takeoff_summary": Reponse(ok=True, resultat=_texte(RESUME_VIDE)),
            "export_report": Reponse(ok=True, resultat=_echec_outil("disque plein")),
        }
        _brancher(monkeypatch, script)
        connecteur = ConnecteurOpenTakeoff()

        resultat = connecteur.executer_confirmee("exporter", chemin=plan_pdf)

        assert resultat.statut is Statut.ECHEC
        assert "disque plein" in resultat.message


class TestErreurOutil:
    def test_une_reponse_sans_isError_n_est_pas_une_erreur(self):
        assert _erreur_outil(Reponse(ok=True, resultat={"structuredContent": {}})) is None

    def test_isError_rend_le_texte_du_message(self):
        reponse = Reponse(ok=True, resultat=_echec_outil("feuille non chargee"))
        assert _erreur_outil(reponse) == "feuille non chargee"
