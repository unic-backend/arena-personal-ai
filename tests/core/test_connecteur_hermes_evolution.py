"""Le connecteur Hermes Agent Self-Evolution : jamais ARENA comme cible,
jamais lancé sans le coupe-circuit `EXECUTE_COMMANDS`.

Contexte (DEC-0055) : demande directe du propriétaire après DEC-0014 (le
Gardien : jamais de PR autonome sur ce dépôt, même relue avant fusion) —
réponse explicite : « construis-le, mais pointe-le sur autre chose que ce
dépôt ARENA ». Aucun `subprocess.run` réel ici : l'outil n'est jamais
installé dans ce conteneur (un programme externe, cloné à côté, comme
OpenTakeoff) — chaque appel est remplacé par un double scripté.
"""
import subprocess
from unittest.mock import patch

import pytest

from core.actions.resultat import Statut
from core.connectors.base import ControleAcces, EtatSante
from core.connectors.hermes_evolution import ITERATIONS_MAX, ConnecteurHermesEvolution
from core.permissions.permission_manager import PermissionManager


@pytest.fixture(autouse=True)
def _configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_EVOLUTION_DIR", str(tmp_path / "outil"))


@pytest.fixture
def connecteur_avec_execute_active(tmp_path):
    """`EXECUTE_COMMANDS` est éteint par défaut dans le vrai
    `config/permissions.yaml` — ces tests vérifient le CHEMIN d'exécution,
    pas ce coupe-circuit précis (déjà vérifié séparément,
    `TestLeCoupeCircuitExecuteCommands`)."""
    permissions = PermissionManager(config_path=str(tmp_path / "booleens.yaml"))
    permissions.permissions.update({"EXECUTE_COMMANDS": True})
    return ConnecteurHermesEvolution(acces=ControleAcces(permissions=permissions))


class FauxCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _double(execution=None):
    """Un double de `subprocess.run` qui distingue la SONDE (`--help`, doit
    reussir pour que `_conduire()` laisse l'execution avoir lieu) de
    l'EXECUTION reelle (`execution`, ce que le test veut observer) — les
    deux passent par le meme `subprocess.run`, jamais confondues.

    `execution` est soit un `FauxCompleted`, soit une exception a lever.
    """
    execution = execution if execution is not None else FauxCompleted(returncode=0)

    def repondre(commande, *args, **kwargs):
        if "--help" in commande:
            return FauxCompleted(returncode=0)
        if isinstance(execution, BaseException):
            raise execution
        return execution

    return repondre


class TestCapacites:
    def test_une_seule_capacite_qui_ecrit(self):
        capacites = ConnecteurHermesEvolution().capacites()
        assert set(capacites) == {"evoluer"}
        assert capacites["evoluer"].ecriture is True
        assert capacites["evoluer"].action == "execute"


class TestSonde:
    def test_sans_dossier_non_configure(self, monkeypatch):
        monkeypatch.delenv("HERMES_EVOLUTION_DIR", raising=False)
        sante = ConnecteurHermesEvolution().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE

    def test_outil_qui_repond_operationnel(self):
        with patch("subprocess.run", return_value=FauxCompleted(returncode=0)) as appel:
            sante = ConnecteurHermesEvolution().sonder()
        assert sante.etat is EtatSante.OPERATIONNEL
        assert appel.call_args.kwargs["timeout"] == 15.0

    def test_outil_en_erreur_en_panne(self):
        with patch("subprocess.run", return_value=FauxCompleted(returncode=1)):
            sante = ConnecteurHermesEvolution().sonder()
        assert sante.etat is EtatSante.EN_PANNE

    def test_outil_introuvable_non_configure(self):
        with patch("subprocess.run", side_effect=OSError("introuvable")):
            sante = ConnecteurHermesEvolution().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE

    def test_sonde_qui_bloque_non_configure(self):
        with patch("subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="x", timeout=15.0)):
            sante = ConnecteurHermesEvolution().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE


class TestCibleJamaisARENA:
    """La garde structurelle centrale de DEC-0055 : quoi qu'on demande,
    ARENA ne peut jamais être la cible de sa propre évolution."""

    def test_le_depot_arena_lui_meme_est_refuse(self, connecteur_avec_execute_active):
        from apps.backend.config import BASE_DIR

        with patch("subprocess.run", side_effect=_double()):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(BASE_DIR), competence="devis")
        assert resultat.statut is Statut.ECHEC
        assert "DEC-0014" in resultat.message

    def test_un_sous_dossier_d_arena_est_refuse(self, connecteur_avec_execute_active):
        from apps.backend.config import BASE_DIR

        with patch("subprocess.run", side_effect=_double()):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(BASE_DIR / "core"), competence="devis")
        assert resultat.statut is Statut.ECHEC

    def test_un_depot_hors_d_arena_est_accepte(self, connecteur_avec_execute_active, tmp_path):
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        with patch("subprocess.run", return_value=FauxCompleted(returncode=0, stdout="ok")):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(cible), competence="devis")
        assert resultat.statut is Statut.SUCCES, resultat.message


class TestValidation:
    def test_sans_depot_cible_est_un_echec(self, connecteur_avec_execute_active):
        with patch("subprocess.run", side_effect=_double()):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible="", competence="devis")
        assert resultat.statut is Statut.ECHEC

    def test_depot_cible_inexistant_est_un_echec(self, connecteur_avec_execute_active, tmp_path):
        with patch("subprocess.run", side_effect=_double()):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(tmp_path / "n-existe-pas"), competence="devis")
        assert resultat.statut is Statut.ECHEC

    def test_sans_competence_est_un_echec(self, connecteur_avec_execute_active, tmp_path):
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        with patch("subprocess.run", side_effect=_double()):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(cible), competence="")
        assert resultat.statut is Statut.ECHEC

    def test_source_evaluation_inconnue_est_un_echec(self, connecteur_avec_execute_active, tmp_path):
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        with patch("subprocess.run", side_effect=_double()):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(cible), competence="devis", source_evaluation="cloud-x")
        assert resultat.statut is Statut.ECHEC

    def test_iterations_hors_bornes_est_un_echec(self, connecteur_avec_execute_active, tmp_path):
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        with patch("subprocess.run", side_effect=_double()):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(cible), competence="devis", iterations=ITERATIONS_MAX + 1)
        assert resultat.statut is Statut.ECHEC

    def test_timeout_hors_bornes_est_un_echec(self, connecteur_avec_execute_active, tmp_path):
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        with patch("subprocess.run", side_effect=_double()):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(cible), competence="devis", timeout_secondes=999999)
        assert resultat.statut is Statut.ECHEC


class TestExecution:
    def test_evolution_reelle_appelle_le_bon_sous_processus(
        self, connecteur_avec_execute_active, tmp_path
    ):
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        with patch("subprocess.run", return_value=FauxCompleted(returncode=0, stdout="fait")) as appel:
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(cible), competence="github-code-review",
                iterations=5, source_evaluation="synthetic")

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.preuve == f"github-code-review@{cible}"
        commande = appel.call_args.args[0]
        assert "--skill" in commande and "github-code-review" in commande
        assert "--iterations" in commande and "5" in commande
        assert appel.call_args.kwargs["env"]["HERMES_AGENT_REPO"] == str(cible.resolve())

    def test_echec_de_l_outil_est_rapporte(self, connecteur_avec_execute_active, tmp_path):
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        execution = FauxCompleted(returncode=1, stderr="synthetic dataset vide")
        with patch("subprocess.run", side_effect=_double(execution)):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(cible), competence="devis")
        assert resultat.statut is Statut.ECHEC
        assert "synthetic dataset vide" in resultat.message

    def test_timeout_est_rapporte_jamais_un_succes(self, connecteur_avec_execute_active, tmp_path):
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        expiration = subprocess.TimeoutExpired(cmd="x", timeout=10.0)
        with patch("subprocess.run", side_effect=_double(expiration)):
            resultat = connecteur_avec_execute_active.executer_confirmee(
                "evoluer", depot_cible=str(cible), competence="devis", timeout_secondes=10.0)
        assert resultat.statut is Statut.ECHEC
        assert "interrompue" in resultat.message

    def test_sans_outil_installe_rend_non_configure(self, connecteur_avec_execute_active,
                                                     monkeypatch, tmp_path):
        monkeypatch.delenv("HERMES_EVOLUTION_DIR", raising=False)
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        resultat = connecteur_avec_execute_active.executer_confirmee(
            "evoluer", depot_cible=str(cible), competence="devis")
        assert resultat.statut is Statut.NON_CONFIGURE


class TestLeCoupeCircuitExecuteCommands:
    def test_evoluer_refuse_sous_execute_commands_eteint_par_defaut(self, tmp_path):
        cible = tmp_path / "hermes-agent"
        cible.mkdir()
        with patch("subprocess.run", return_value=FauxCompleted(returncode=0)) as appel:
            resultat = ConnecteurHermesEvolution().executer_confirmee(
                "evoluer", depot_cible=str(cible), competence="devis")
        assert resultat.statut is Statut.REFUSE
        appel.assert_not_called()


class TestLaVraiePolitiqueLivree:
    def test_evoluer_reste_sous_execute_commands_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        politique = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE)
        regle = politique.regle("hermes_evolution", "execute")
        assert regle is not None, "hermes_evolution.execute a disparu de la politique livree"
        assert regle.get("decision") == "CONFIRMATION"
        assert regle.get("interrupteur") == "EXECUTE_COMMANDS"
