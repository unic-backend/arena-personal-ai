"""La vérification formelle : ce qui est prouvé, et ce qui a seulement compilé.

**Le test qui compte est `TestCompilerNEstPasProuver`.** Une preuve trouée
(`sorry`) compile avec le code de sortie **0** — mesuré le 07/09/2026 :

    theorem troue (n : Nat) : n + 0 = n := by sorry
    -> code 0, et « depends on axioms: [sorryAx] »

Juger sur le code de sortie aurait donc déclaré VÉRIFIÉE une preuve vide.
C'est exactement la discipline reprise du dépôt `anthropics/fermats-last-theorem`
(Apache-2.0), qui épingle les axiomes de son théorème final plutôt que de se
fier à la compilation.

Les tests marqués `integration` exigent le vrai binaire Lean ; les autres
tiennent sur une machine où il n'y a rien — c'est le cas du CI. **Sauter
n'est pas passer**, et le rapport de pytest le dit.
"""
import subprocess
from pathlib import Path

import pytest

import core.connectors.lean_formel as module
from core.actions.resultat import Statut
from core.connectors.lean_formel import (
    AXIOMES_DE_CONFIANCE,
    ConnecteurLeanFormel,
    axiomes_declares,
    chemin_de_lean,
    famille_d_erreur,
    nom_du_theoreme,
)

#: Lean n'est pas installé sur le CI — c'est un moteur externe, comme
#: VoiceStudio ou Chromium. Les mesures qui l'exigent sont sautées là-bas.
_SANS_LEAN = pytest.mark.skipif(
    chemin_de_lean() is None,
    reason="Lean absent : aucune vérification réelle ne peut être mesurée ici")


class TestLaPermissionPasseAvantTout:
    """Lean est un langage à métaprogrammation : vérifier une source qu'un
    modèle a écrite, c'est exécuter du code. L'action est donc gouvernée par
    `EXECUTE_COMMANDS`, **éteint par défaut** — et ce test le mesure sur la
    configuration réelle du dépôt, pas sur une intention écrite.
    """

    def test_sans_execute_commands_rien_n_est_verifie(self, tmp_path, monkeypatch):
        from core.permissions.controle import ControleAcces
        from core.permissions.permission_manager import PermissionManager
        from core.permissions.politique import PolitiqueDePermissions

        acces = ControleAcces(permissions=PermissionManager(),
                              politique=PolitiqueDePermissions())
        connecteur = ConnecteurLeanFormel(dossier=tmp_path, acces=acces)
        monkeypatch.setattr(
            connecteur, "_verifier",
            lambda **k: pytest.fail("la preuve a ete verifiee malgre le coupe-circuit"))

        r = connecteur.executer("verifier", source="theorem t : 2 + 2 = 4 := by rfl")

        assert r.statut is Statut.REFUSE
        assert "EXECUTE_COMMANDS" in r.message


class TestLaLectureDesAxiomes:
    """C'est là que se joue « prouvé » contre « admis »."""

    def test_aucun_axiome_est_une_liste_vide_pas_un_silence(self):
        assert axiomes_declares("'t' does not depend on any axioms") == []

    def test_les_axiomes_sont_lus_tels_quels(self):
        lu = axiomes_declares("'t' depends on axioms: [propext, Classical.choice]")
        assert lu == ["propext", "Classical.choice"]

    def test_un_sorry_se_lit_comme_un_axiome_ajoute(self):
        assert axiomes_declares("'t' depends on axioms: [sorryAx]") == ["sorryAx"]

    def test_un_silence_de_lean_n_est_pas_une_liste_vide(self):
        """« Lean ne s'est pas prononcé » et « aucun axiome » sont deux
        constats différents. Les confondre déclarerait vérifiée une preuve
        que personne n'a interrogée."""
        assert axiomes_declares("") is None
        assert axiomes_declares("des diagnostics sans rapport") is None

    def test_sorryax_n_est_pas_un_axiome_de_confiance(self):
        assert "sorryAx" not in AXIOMES_DE_CONFIANCE
        assert AXIOMES_DE_CONFIANCE == {"propext", "Classical.choice", "Quot.sound"}


class TestLeNomDuTheoreme:
    """Sans nom, aucun `#print axioms` — donc aucune preuve de complétude."""

    @pytest.mark.parametrize("source,attendu", [
        ("theorem simple : True := by trivial", "simple"),
        ("lemma petit_lemme : True := by trivial", "petit_lemme"),
        ("private theorem cache : True := by trivial", "cache"),
        ("noncomputable theorem lourd : True := by trivial", "lourd"),
    ])
    def test_le_premier_theoreme_est_reconnu(self, source, attendu):
        assert nom_du_theoreme(source) == attendu

    def test_une_source_sans_theoreme_ne_rend_aucun_nom(self):
        assert nom_du_theoreme("def f (n : Nat) : Nat := n + 1") is None


class TestCeQuiEstRefuseAvantDeLancerLean:
    """Rien ne part vers un processus tant que la source n'est pas saine."""

    def test_une_source_vide_est_un_echec(self, tmp_path):
        r = ConnecteurLeanFormel(dossier=tmp_path)._verifier(source="   ")
        assert r.statut is Statut.ECHEC
        assert "rien a verifier" in r.message

    def test_une_source_sans_theoreme_est_refusee_avec_sa_raison(self, tmp_path):
        r = ConnecteurLeanFormel(dossier=tmp_path)._verifier(
            source="def f (n : Nat) : Nat := n")
        assert r.statut is Statut.ECHEC
        assert "axiomes" in r.message

    @pytest.mark.parametrize("source", [
        "theorem t : True := by trivial\n#eval IO.Process.run { cmd := \"ls\" }",
        "theorem t : True := by trivial\nunsafe def x : Nat := 0",
        "theorem t : True := by trivial\n#eval IO.FS.readFile \"/etc/passwd\"",
    ])
    def test_une_source_qui_veut_s_executer_ne_lance_jamais_lean(
        self, tmp_path, monkeypatch, source
    ):
        """Une preuve n'a aucun besoin de lancer un processus ni de lire le
        disque. Le refus doit tomber AVANT le binaire, pas après."""
        connecteur = ConnecteurLeanFormel(dossier=tmp_path)
        monkeypatch.setattr(
            connecteur, "_lancer_lean",
            lambda *a, **k: pytest.fail("Lean a été lancé sur une source d'exécution"))

        r = connecteur._verifier(source=source)

        assert r.statut is Statut.ECHEC
        assert r.detail["refus"] == "execution_a_la_compilation"

    def test_une_source_demesuree_est_refusee(self, tmp_path):
        enorme = "theorem t : True := by trivial\n" + ("-- bla\n" * 40000)
        r = ConnecteurLeanFormel(dossier=tmp_path)._verifier(source=enorme)
        assert r.statut is Statut.ECHEC
        assert "trop longue" in r.message


class TestSansLean:
    """Lean absent : rien n'est simulé, et surtout rien n'est « vérifié »."""

    def test_la_sante_dit_ce_qui_manque(self, monkeypatch, tmp_path):
        monkeypatch.setattr(module, "chemin_de_lean", lambda: None)
        sante = ConnecteurLeanFormel(dossier=tmp_path).sante()
        assert not sante.utilisable
        assert "Lean" in sante.ce_qui_manque

    def test_aucune_preuve_n_est_verifiee_sans_binaire(self, monkeypatch, tmp_path):
        monkeypatch.setattr(module, "chemin_de_lean", lambda: None)
        r = ConnecteurLeanFormel(dossier=tmp_path)._verifier(
            source="theorem t : 2 + 2 = 4 := by rfl")
        assert r.statut is not Statut.SUCCES


class TestLesFamillesDErreur:
    """Un diagnostic de compilateur sert à réparer : il ne se cache pas."""

    @pytest.mark.parametrize("sortie,attendu", [
        ("error: unknown identifier 'foo'", "identifiant inconnu"),
        ("error: unsolved goals\n⊢ False", "but non demontre"),
        ("error: type mismatch", "type incompatible"),
        ("is not definitionally equal to", "egalite non verifiable par calcul"),
        ("error: unexpected token", "erreur de syntaxe"),
    ])
    def test_l_erreur_est_nommee_en_francais(self, sortie, attendu):
        assert famille_d_erreur(sortie) == attendu

    def test_une_sortie_inconnue_ne_recoit_pas_une_famille_inventee(self):
        assert famille_d_erreur("quelque chose de jamais vu") is None


class TestCapacites:
    def test_verifier_ne_modifie_rien_hors_d_arena(self, tmp_path):
        capacites = ConnecteurLeanFormel(dossier=tmp_path).capacites()
        assert capacites["verifier"].ecriture is False

    def test_le_service_est_celui_declare_dans_les_permissions(self, tmp_path):
        assert ConnecteurLeanFormel(dossier=tmp_path).service == "lean_formel"

    def test_l_action_passe_par_son_propre_interrupteur(self, tmp_path):
        """`verifier` doit avoir sa propre entrée : Lean exécute un processus,
        et cette action est gouvernée par EXECUTE_COMMANDS, éteint par défaut."""
        import yaml

        racine = Path(__file__).resolve().parent.parent.parent
        regles = yaml.safe_load(
            (racine / "config" / "permissions_services.yaml").read_text(encoding="utf-8"))
        entree = regles["services"]["lean_formel"]["verifier"]

        assert entree["interrupteur"] == "EXECUTE_COMMANDS"


# --- Ce qui exige le vrai Lean --------------------------------------------------


@_SANS_LEAN
class TestAvecLeanReel:
    """Le binaire tourne vraiment. Aucun de ces verdicts n'est simulé."""

    def test_la_sante_rapporte_la_version_mesuree(self, tmp_path):
        sante = ConnecteurLeanFormel(dossier=tmp_path).sante()
        assert sante.utilisable
        assert "Lean" in sante.message and sante.mesure_le

    def test_une_preuve_valide_est_acceptee(self, tmp_path):
        r = ConnecteurLeanFormel(dossier=tmp_path)._verifier(
            source="theorem deux_plus_deux : 2 + 2 = 4 := by rfl")

        assert r.statut is Statut.SUCCES, r.message
        assert r.detail["verdict"] == "VERIFIE"
        assert r.detail["axiomes_ajoutes"] == []
        assert Path(r.preuve).is_file(), "l'artefact de la preuve n'a pas ete garde"

    def test_une_preuve_fausse_est_rejetee_avec_son_diagnostic(self, tmp_path):
        r = ConnecteurLeanFormel(dossier=tmp_path)._verifier(
            source="theorem faux : 2 + 2 = 5 := by rfl")

        assert r.statut is Statut.ECHEC
        assert r.detail["verdict"] == "REJETE"
        assert r.detail["code"] != 0
        assert r.detail["diagnostics"], "le diagnostic de Lean a ete perdu"

    def test_un_theoreme_qui_n_existe_pas_est_rejete(self, tmp_path):
        r = ConnecteurLeanFormel(dossier=tmp_path)._verifier(
            source="theorem t : 2 + 2 = 4 := by exact monTacticInexistant")
        assert r.statut is Statut.ECHEC
        assert r.detail["verdict"] == "REJETE"


@_SANS_LEAN
class TestCompilerNEstPasProuver:
    """**Le test central de ce module**, et la raison qu'il existe.

    Mesuré le 07/09/2026 avec le vrai binaire : une preuve trouée compile et
    rend le code de sortie **0**. Un module qui jugerait sur ce code aurait
    déclaré VÉRIFIÉE une démonstration vide — le `SUCCESS` sans preuve que
    `core/actions/resultat.py` refuse de construire.

    La discipline vient de `FinalCheck.lean` du dépôt Fermat : on interroge
    les axiomes, on ne se fie pas à la compilation.
    """

    SOURCE_TROUEE = "theorem troue (n : Nat) : n + 0 = n := by sorry"

    def test_lean_lui_meme_accepte_de_compiler_la_preuve_trouee(self, tmp_path):
        """Le fait de départ, mesuré ici et pas supposé : sans cette réalité,
        tout le reste du module serait de la précaution inutile."""
        binaire = chemin_de_lean()
        fichier = tmp_path / "Troue.lean"
        fichier.write_text(self.SOURCE_TROUEE + "\n", encoding="utf-8")

        sortie = subprocess.run([str(binaire), fichier.name], cwd=str(tmp_path),
                                capture_output=True, text=True, timeout=120)

        assert sortie.returncode == 0, (
            "si Lean refusait deja les preuves trouees, ce module n'aurait pas "
            "besoin de lire les axiomes — la mesure dit qu'il les accepte")

    def test_arena_la_rejette_quand_meme(self, tmp_path):
        r = ConnecteurLeanFormel(dossier=tmp_path)._verifier(source=self.SOURCE_TROUEE)

        assert r.statut is Statut.ECHEC, (
            "une preuve trouee s'est fait passer pour verifiee")
        assert r.detail["verdict"] == "REJETE"
        assert r.detail["troue"] is True
        assert r.detail["axiomes"] == ["sorryAx"]
        assert r.detail["code"] == 0, (
            "le rejet doit venir des axiomes, pas du code de sortie")

    def test_aucun_artefact_n_est_garde_pour_une_preuve_trouee(self, tmp_path):
        dossier = tmp_path / "preuves"
        ConnecteurLeanFormel(dossier=dossier)._verifier(source=self.SOURCE_TROUEE)

        restes = list(dossier.glob("*.lean")) if dossier.exists() else []
        assert restes == [], f"une preuve non verifiee a laisse un artefact : {restes}"


@_SANS_LEAN
class TestRienNeTourneSansBorne:
    def test_un_delai_depasse_est_un_echec_nomme_pas_un_verdict(self, tmp_path):
        """Un dépassement de temps ne dit RIEN sur la vérité du théorème :
        il ne doit donc jamais ressortir comme un rejet mathématique."""
        r = ConnecteurLeanFormel(dossier=tmp_path)._verifier(
            source="theorem lent : 2 + 2 = 4 := by rfl", delai=0.001)

        assert r.statut is Statut.ECHEC
        assert r.detail["verdict"] == "DELAI"
        assert r.detail["verdict"] != "REJETE"
