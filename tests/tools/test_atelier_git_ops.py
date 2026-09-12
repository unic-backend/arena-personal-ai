"""`Atelier.git_stager` à `git_abandonner` (DEC-0094, mission ARENA x GITGUI,
second passage) — que l'atelier appelle bien `git_ops`, journalise, et
partage UN SEUL `JournalOperationsGit` sur sa durée de vie (l'idempotence ne
veut rien dire si chaque appel reconstruit son propre journal vide).

`git_ops.py` a sa propre suite (`tests/tools/test_git_ops.py`) qui couvre le
détail du mécanisme. Ici : le câblage `Atelier`, pas le mécanisme lui-même.
"""
import subprocess
from pathlib import Path

import pytest

from tools.atelier.atelier import Atelier


def _git(racine: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=str(racine), capture_output=True,
                   text=True, check=True)


@pytest.fixture
def depot(tmp_path) -> Path:
    racine = tmp_path / "depot"
    racine.mkdir()
    _git(racine, "init", "-q", "-b", "main")
    _git(racine, "config", "user.email", "test@test.local")
    _git(racine, "config", "user.name", "test")
    (racine / "a.txt").write_text("contenu initial\n", encoding="utf-8")
    _git(racine, "add", "-A")
    _git(racine, "commit", "-q", "-m", "initial")
    return racine


class TestStagerCommettre:
    def test_stager_puis_commettre(self, depot):
        atelier = Atelier(racine=depot)
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        rs = atelier.git_stager(["a.txt"])
        assert rs.ok
        rc = atelier.git_commettre("modif")
        assert rc.ok
        assert rc.donnees["tete_apres"] != rc.donnees["tete_avant"]

    def test_idempotence_partagee_sur_la_duree_de_vie_de_l_atelier(self, depot):
        atelier = Atelier(racine=depot)
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        atelier.git_stager(["a.txt"])

        r1 = atelier.git_commettre("modif", identifiant_operation="op-1")
        r2 = atelier.git_commettre("modif", identifiant_operation="op-1")

        assert r1.donnees["doublon"] is False
        assert r2.donnees["doublon"] is True
        assert r1.donnees["tete_apres"] == r2.donnees["tete_apres"]
        log = subprocess.run(["git", "log", "--oneline"], cwd=str(depot),
                             capture_output=True, text=True, check=True).stdout
        assert len(log.splitlines()) == 2


class TestBranchesEtBascule:
    def test_creer_branche_et_lister(self, depot):
        atelier = Atelier(racine=depot)
        r = atelier.git_branche_creer("feature-x")
        assert r.ok
        rl = atelier.git_branches_lister()
        assert rl.ok
        noms = {b["nom"] for b in rl.donnees["donnees"]["branches"]}
        assert "feature-x" in noms

    def test_basculer_verifie_reellement(self, depot):
        atelier = Atelier(racine=depot)
        atelier.git_branche_creer("feature-y", basculer=False)
        r = atelier.git_basculer("feature-y")
        assert r.ok


class TestPreconditionEtRefus:
    def test_tete_attendue_perimee_refuse(self, depot):
        atelier = Atelier(racine=depot)
        st = atelier.git_statut()
        tete = st.donnees["tete"]
        _git(depot, "commit", "--allow-empty", "-q", "-m", "externe")

        (depot / "a.txt").write_text("x\n", encoding="utf-8")
        atelier.git_stager(["a.txt"])
        r = atelier.git_commettre("refuse", tete_attendue=tete)
        assert r.ok is False


class TestConflitEtRecuperation:
    def test_fusion_conflictuelle_lecture_resolution_continuation(self, depot):
        atelier = Atelier(racine=depot)
        _git(depot, "checkout", "-q", "-b", "branche-a")
        (depot / "a.txt").write_text("version A\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "a")
        _git(depot, "checkout", "-q", "main")
        (depot / "a.txt").write_text("version B\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "b")

        rf = atelier.git_fusionner("branche-a")
        assert rf.ok is False

        rc = atelier.git_conflit_lire("a.txt")
        assert rc.ok
        assert rc.donnees["donnees"]["notre_version"] == "version B\n"

        (depot / "a.txt").write_text("resolu\n", encoding="utf-8")
        atelier.git_stager(["a.txt"])
        rcont = atelier.git_continuer()
        assert rcont.ok

    def test_abandonner_revient_a_un_etat_propre(self, depot):
        atelier = Atelier(racine=depot)
        _git(depot, "checkout", "-q", "-b", "branche-a")
        (depot / "a.txt").write_text("version A\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "a")
        _git(depot, "checkout", "-q", "main")
        (depot / "a.txt").write_text("version B\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "b")

        atelier.git_fusionner("branche-a")
        r = atelier.git_abandonner()
        assert r.ok


class TestTagRemise:
    def test_creer_tag(self, depot):
        atelier = Atelier(racine=depot)
        r = atelier.git_tag_creer("v1.0.0", message="premiere")
        assert r.ok

    def test_remiser_et_appliquer(self, depot):
        atelier = Atelier(racine=depot)
        (depot / "a.txt").write_text("en cours\n", encoding="utf-8")
        r1 = atelier.git_remiser(message="wip")
        assert r1.ok
        assert (depot / "a.txt").read_text(encoding="utf-8") == "contenu initial\n"
        r2 = atelier.git_remise_appliquer()
        assert r2.ok
        assert (depot / "a.txt").read_text(encoding="utf-8") == "en cours\n"


class TestPousserJamaisForceNu:
    def test_signature_n_expose_pas_force_nu(self):
        import inspect
        signature = inspect.signature(Atelier.git_pousser)
        assert "force" not in signature.parameters
        assert "force_avec_bail" in signature.parameters
