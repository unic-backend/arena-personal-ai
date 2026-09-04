"""Le connecteur Graphify dit-il la verite sur ce qu'il sait du depot ?

Deux familles de tests, comme pour OpenTakeoff (`test_connecteur_opentakeoff.py`)
et Faceplugin (`test_connecteur_faceplugin.py`) :

1. **Le contrat, sans le vrai moteur** : `subprocess.run` est remplace par un
   double scripte. Ces tests tournent partout, meme sans `graphify` installe.
2. **Le vrai moteur, sur un fixture jetable** (`moteur_reel`, sautee si
   `graphify` n'est pas sur le PATH — mesure, jamais simulee) : construit un
   VRAI graphe sur un petit dossier de code fabrique pour l'occasion, jamais
   sur ce depot lui-meme (trop lent pour un test, et pas son role — le vrai
   graphe du depot se construit a la demande, voir DEC-0046) ni sur un
   document client (aucun ici : ce connecteur ne touche que du code).
"""
import json
import subprocess
from typing import Any, Dict

import pytest
import yaml

import core.connectors.graphify as graphify_mod
from core.actions.resultat import Statut
from core.connectors.base import ControleAcces, EtatSante
from core.connectors.graphify import ConnecteurGraphify
from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import PolitiqueDePermissions

moteur_reel = pytest.mark.skipif(
    graphify_mod.shutil.which(graphify_mod.GRAPHIFY_BIN) is None,
    reason="graphify n'est pas installe : mesure impossible, donc non simulee")


@pytest.fixture
def graphe_absent(monkeypatch, tmp_path):
    """Le binaire est present, mais aucun graph.json n'existe encore."""
    monkeypatch.setattr(graphify_mod, "RACINE", tmp_path)
    monkeypatch.setattr(graphify_mod, "DOSSIER_GRAPHE", tmp_path / "graphify-out")
    monkeypatch.setattr(graphify_mod, "GRAPH_JSON", tmp_path / "graphify-out" / "graph.json")
    monkeypatch.setattr(graphify_mod, "_binaire_present", lambda: True)
    return tmp_path


@pytest.fixture
def graphe_construit(graphe_absent):
    """Un graph.json minimal mais valide, de la forme reelle (nodes/links)."""
    graphify_mod.DOSSIER_GRAPHE.mkdir(parents=True, exist_ok=True)
    graphify_mod.GRAPH_JSON.write_text(json.dumps({
        "directed": True, "multigraph": False, "graph": {},
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "links": [{"source": "a", "target": "b", "relation": "calls"}],
    }), encoding="utf-8")
    return graphe_absent


def _double_subprocess(script: Dict[str, Any]):
    """Remplace `ConnecteurGraphify._lancer` par un double indexe sur le sous-commande.

    `script["update"]` (par exemple) est un `subprocess.CompletedProcess`, ou
    une fabrique `args -> CompletedProcess` pour verifier les arguments reçus.
    """

    def _lancer(self, arguments, delai):
        sous_commande = arguments[0]
        fabrique = script.get(sous_commande)
        if fabrique is None:
            return subprocess.CompletedProcess(args=arguments, returncode=1,
                                                stdout="", stderr="non scripte")
        return fabrique(arguments) if callable(fabrique) else fabrique

    return _lancer


class TestCapacitesEtSante:
    def test_cinq_capacites_declarees(self):
        connecteur = ConnecteurGraphify()
        noms = set(connecteur.capacites())
        assert noms == {"construire", "interroger", "chemin", "expliquer", "hubs"}

    def test_seul_construire_ecrit(self):
        capacites = ConnecteurGraphify().capacites()
        assert capacites["construire"].ecriture is True
        for nom in ("interroger", "chemin", "expliquer", "hubs"):
            assert capacites[nom].ecriture is False, f"{nom} ne devrait rien ecrire"

    def test_authentifier_toujours_vrai(self):
        assert ConnecteurGraphify().authentifier() is True

    def test_sonde_non_configure_sans_binaire(self, monkeypatch):
        monkeypatch.setattr(graphify_mod, "_binaire_present", lambda: False)
        sante = ConnecteurGraphify().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "installe" in sante.message

    def test_sonde_operationnel_meme_sans_graphe(self, graphe_absent):
        """L'engin est joignable des le premier appel : sinon « construire »,
        qui doit precisement PRODUIRE ce graphe, ne pourrait jamais s'executer
        — `_conduire()` (base.py) bloque toute capacite tant que la sante
        n'est pas OPERATIONNEL, y compris celle qui construirait le graphe."""
        sante = ConnecteurGraphify().sonder()
        assert sante.etat is EtatSante.OPERATIONNEL
        assert "aucun graphe" in sante.message

    def test_sonde_reste_operationnel_si_graph_json_illisible(self, graphe_absent):
        """Un graph.json corrompu n'est pas une panne du moteur : « construire »
        doit rester joignable pour le reparer. Chaque lecture le detecte a son
        tour (la commande graphify echoue alors, capte comme ECHEC)."""
        graphify_mod.DOSSIER_GRAPHE.mkdir(parents=True, exist_ok=True)
        graphify_mod.GRAPH_JSON.write_text("{ pas du json", encoding="utf-8")

        sante = ConnecteurGraphify().sonder()

        assert sante.etat is EtatSante.OPERATIONNEL
        assert "ne se charge pas" in sante.message

    def test_sonde_operationnel_avec_le_vrai_compte(self, graphe_construit):
        sante = ConnecteurGraphify().sonder()
        assert sante.etat is EtatSante.OPERATIONNEL
        assert "2 noeud(s)" in sante.message
        assert "1 lien(s)" in sante.message


class TestExecutionSansGraphe:
    """Les quatre lectures refusent proprement quand rien n'a ete construit —
    jamais une reponse plausible a la place d'un graphe absent."""

    @pytest.mark.parametrize("capacite,parametres", [
        ("interroger", {"question": "quoi ?"}),
        ("chemin", {"depuis": "A", "vers": "B"}),
        ("expliquer", {"noeud": "A"}),
        ("hubs", {}),
    ])
    def test_non_configure_sans_graphe(self, graphe_absent, capacite, parametres):
        connecteur = ConnecteurGraphify()
        resultat = connecteur.executer_confirmee(capacite, **parametres)
        assert resultat.statut is Statut.NON_CONFIGURE, resultat.message


class TestConstruire:
    def test_construire_reussit(self, graphe_absent, monkeypatch):
        def _update(arguments):
            graphify_mod.DOSSIER_GRAPHE.mkdir(parents=True, exist_ok=True)
            graphify_mod.GRAPH_JSON.write_text(json.dumps(
                {"nodes": [{"id": "a"}], "links": []}), encoding="utf-8")
            return subprocess.CompletedProcess(args=arguments, returncode=0,
                                               stdout="Rebuilt: 1 nodes, 0 edges", stderr="")

        monkeypatch.setattr(ConnecteurGraphify, "_lancer", _double_subprocess({"update": _update}))

        resultat = ConnecteurGraphify().executer_confirmee("construire")

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["noeuds"] == 1

    def test_construire_pointe_la_racine_du_depot(self, graphe_absent, monkeypatch):
        """La commande doit porter sur la racine reelle, jamais un chemin devine."""
        recu = {}

        def _capturer_lancer(self, arguments, delai):
            recu["arguments"] = arguments
            return subprocess.CompletedProcess(args=arguments, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(ConnecteurGraphify, "_lancer", _capturer_lancer)

        ConnecteurGraphify().executer_confirmee("construire")

        assert recu["arguments"][0] == "update"
        assert recu["arguments"][1] == str(graphify_mod.RACINE)

    def test_construire_echec_code_non_nul(self, graphe_absent, monkeypatch):
        monkeypatch.setattr(ConnecteurGraphify, "_lancer", _double_subprocess({
            "update": subprocess.CompletedProcess(args=[], returncode=1,
                                                   stdout="", stderr="boom")}))

        resultat = ConnecteurGraphify().executer_confirmee("construire")

        assert resultat.statut is Statut.ECHEC
        assert "boom" in resultat.message

    def test_construire_timeout_est_un_echec_pas_un_crash(self, graphe_absent, monkeypatch):
        def _lever(self, arguments, delai):
            raise subprocess.TimeoutExpired(cmd="graphify", timeout=delai)

        monkeypatch.setattr(ConnecteurGraphify, "_lancer", _lever)

        resultat = ConnecteurGraphify().executer_confirmee("construire")

        assert resultat.statut is Statut.ECHEC
        assert "depasse" in resultat.message


class TestLecturesAvecGraphe:
    def test_interroger_relaie_la_sortie(self, graphe_construit, monkeypatch):
        monkeypatch.setattr(ConnecteurGraphify, "_lancer", _double_subprocess({
            "query": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="NODE A [src=x.py]\n", stderr="")}))

        resultat = ConnecteurGraphify().executer_confirmee("interroger", question="qui est A ?")

        assert resultat.statut is Statut.SUCCES
        assert "NODE A" in resultat.message

    def test_chemin_relaie_la_sortie(self, graphe_construit, monkeypatch):
        monkeypatch.setattr(ConnecteurGraphify, "_lancer", _double_subprocess({
            "path": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="A --calls--> B\n", stderr="")}))

        resultat = ConnecteurGraphify().executer_confirmee("chemin", depuis="A", vers="B")

        assert resultat.statut is Statut.SUCCES
        assert "A --calls--> B" in resultat.message

    def test_expliquer_relaie_la_sortie(self, graphe_construit, monkeypatch):
        monkeypatch.setattr(ConnecteurGraphify, "_lancer", _double_subprocess({
            "explain": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="Node: A\n  Degree: 1\n", stderr="")}))

        resultat = ConnecteurGraphify().executer_confirmee("expliquer", noeud="A")

        assert resultat.statut is Statut.SUCCES
        assert "Degree: 1" in resultat.message

    def test_hubs_parse_le_json(self, graphe_construit, monkeypatch):
        monkeypatch.setattr(ConnecteurGraphify, "_lancer", _double_subprocess({
            "god-nodes": subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout=json.dumps([{"label": "A", "degree": 9}]), stderr="")}))

        resultat = ConnecteurGraphify().executer_confirmee("hubs", top=5)

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["hubs"] == [{"label": "A", "degree": 9}]
        assert "A (9)" in resultat.message

    def test_hubs_json_illisible_est_un_echec_pas_un_crash(self, graphe_construit, monkeypatch):
        monkeypatch.setattr(ConnecteurGraphify, "_lancer", _double_subprocess({
            "god-nodes": subprocess.CompletedProcess(
                args=[], returncode=0, stdout="pas du json", stderr="")}))

        resultat = ConnecteurGraphify().executer_confirmee("hubs")

        assert resultat.statut is Statut.ECHEC

    def test_interroger_sans_question_est_un_echec_immediat(self, graphe_construit):
        resultat = ConnecteurGraphify().executer_confirmee("interroger", question="")
        assert resultat.statut is Statut.ECHEC


class TestLeCoupeCircuitWriteFilesBloqueEncoreLaConstruction:
    """Retirer la confirmation n'a jamais retire la protection : le meme
    principe que `test_connecteur_devis.py::test_le_coupe_circuit_...`."""

    def test_construire_refuse_sous_write_files_eteint(self, graphe_absent, tmp_path, monkeypatch):
        politique = tmp_path / "politique.yaml"
        politique.write_text(yaml.safe_dump({"services": {"graphify": {"document": {
            "decision": "ALLOWED", "risque": "LOW", "interrupteur": "WRITE_FILES"}}}}),
            encoding="utf-8")
        permissions = PermissionManager(config_path=str(tmp_path / "booleens.yaml"))
        permissions.permissions.update({"WRITE_FILES": False})

        # Le sous-processus ne doit jamais etre appele : le refus arrive avant.
        appele = {"oui": False}
        monkeypatch.setattr(ConnecteurGraphify, "_lancer",
                            lambda self, arguments, delai: appele.__setitem__("oui", True))

        connecteur = ConnecteurGraphify(
            acces=ControleAcces(permissions=permissions,
                                politique=PolitiqueDePermissions(chemin=politique)))

        resultat = connecteur.executer("construire")

        assert resultat.statut is Statut.REFUSE, resultat.message
        assert appele["oui"] is False, "le sous-processus a tourne malgre WRITE_FILES eteint"


class TestLaVraiePolitiqueLivree:
    """Comme pour le devis (DEC-0041) : ce que dit le VRAI fichier de
    politique, pas une politique fabriquee par le test."""

    def test_construire_reste_sous_write_files_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("graphify", "document")

        assert regle is not None, "graphify.document a disparu de la politique livree"
        assert regle.get("interrupteur") == "WRITE_FILES", (
            "construire n'est plus protege par le coupe-circuit WRITE_FILES")

    def test_les_lectures_sont_permises_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("graphify", "read")

        assert regle is not None
        assert regle.get("decision") == "ALLOWED"


@moteur_reel
class TestLeVraiMoteur:
    """Le vrai binaire `graphify`, sur un fixture jetable — jamais sur ce
    depot (trop lent pour un test) ni sur un document client (aucun ici)."""

    @pytest.fixture
    def petit_projet(self, tmp_path):
        """Deux fichiers Python avec une relation d'heritage reelle a trouver."""
        (tmp_path / "base.py").write_text(
            "class Connecteur:\n    def sonder(self):\n        pass\n", encoding="utf-8")
        (tmp_path / "devis.py").write_text(
            "from base import Connecteur\n\n"
            "class DevisConnector(Connecteur):\n"
            "    def sonder(self):\n        return True\n", encoding="utf-8")
        return tmp_path

    def test_construire_puis_interroger_pour_de_vrai(self, petit_projet, monkeypatch):
        monkeypatch.setattr(graphify_mod, "RACINE", petit_projet)
        monkeypatch.setattr(graphify_mod, "DOSSIER_GRAPHE", petit_projet / "graphify-out")
        monkeypatch.setattr(graphify_mod, "GRAPH_JSON",
                            petit_projet / "graphify-out" / "graph.json")

        connecteur = ConnecteurGraphify()

        construction = connecteur.executer_confirmee("construire")
        assert construction.statut is Statut.SUCCES, construction.message
        assert construction.detail["noeuds"] > 0
        assert (petit_projet / "graphify-out" / "graph.json").is_file()

        sante = connecteur.sonder()
        assert sante.etat is EtatSante.OPERATIONNEL

        explication = connecteur.executer_confirmee("expliquer", noeud="DevisConnector")
        assert explication.statut is Statut.SUCCES, explication.message
        assert "DevisConnector" in explication.message

        chemin = connecteur.executer_confirmee(
            "chemin", depuis="DevisConnector", vers="Connecteur")
        assert chemin.statut is Statut.SUCCES, chemin.message
        assert "Connecteur" in chemin.message
