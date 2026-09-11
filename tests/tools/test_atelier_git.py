"""`Atelier.git_statut`/`git_diff`/`git_checkpoint`/`git_restaurer`
(DEC-0093, mission ARENA x GITGUI) — sur de vrais dépôts git.

`git_etat.py` a déjà sa propre suite (`tests/tools/test_git_etat.py`) qui
couvre le détail du parsing. Ici : que l'atelier appelle bien ce module,
journalise, et rend un `Resultat` correct — sans reparser ce que
`test_git_etat.py` a déjà prouvé.
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
    _git(racine, "init", "-q")
    _git(racine, "config", "user.email", "test@test.local")
    _git(racine, "config", "user.name", "test")
    (racine / "a.txt").write_text("contenu initial\n", encoding="utf-8")
    _git(racine, "add", "-A")
    _git(racine, "commit", "-q", "-m", "initial")
    return racine


class TestGitStatut:
    def test_rend_un_resume_et_les_donnees_structurees(self, depot):
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        atelier = Atelier(racine=depot)

        resultat = atelier.git_statut()

        assert resultat.ok
        assert resultat.donnees["propre"] is False
        assert resultat.donnees["modifies"][0]["chemin"] == "a.txt"

    def test_un_dossier_sans_depot_est_un_echec_nomme(self, tmp_path):
        pas_un_depot = tmp_path / "vide"
        pas_un_depot.mkdir()
        atelier = Atelier(racine=pas_un_depot)

        resultat = atelier.git_statut()

        assert resultat.ok is False


class TestGitDiff:
    def test_rend_le_vrai_texte_du_diff(self, depot):
        (depot / "a.txt").write_text("contenu initial\najoute\n", encoding="utf-8")
        atelier = Atelier(racine=depot)

        resultat = atelier.git_diff(cible="travail")

        assert resultat.ok
        assert "+ajoute" in resultat.sortie
        assert resultat.donnees["fichiers"][0]["chemin"] == "a.txt"


class TestGitCheckpointEtRestaurer:
    def test_cycle_complet_creer_modifier_restaurer(self, depot):
        atelier = Atelier(racine=depot)

        checkpoint = atelier.git_checkpoint()
        assert checkpoint.ok
        identifiant = checkpoint.donnees["identifiant"]

        atelier.ecrire(str(depot / "cree_par_agent.txt"), "x")
        (depot / "a.txt").write_text("modifie par agent\n", encoding="utf-8")

        restauration = atelier.git_restaurer(identifiant)

        assert restauration.ok
        assert not (depot / "cree_par_agent.txt").exists()
        assert (depot / "a.txt").read_text(encoding="utf-8") == "contenu initial\n"

    def test_ne_touche_jamais_un_fichier_deja_dirty_au_checkpoint(self, depot):
        (depot / "a.txt").write_text("deja modifie par le proprietaire\n", encoding="utf-8")
        atelier = Atelier(racine=depot)

        checkpoint = atelier.git_checkpoint()
        (depot / "a.txt").write_text(
            "deja modifie par le proprietaire\nplus agent\n", encoding="utf-8")

        restauration = atelier.git_restaurer(checkpoint.donnees["identifiant"])

        assert restauration.donnees["ignores_deja_dirty"] == ["a.txt"]
        assert (depot / "a.txt").read_text(encoding="utf-8") == (
            "deja modifie par le proprietaire\nplus agent\n")

    def test_un_checkpoint_deja_consomme_ne_peut_pas_etre_rejoue(self, depot):
        atelier = Atelier(racine=depot)
        checkpoint = atelier.git_checkpoint()
        identifiant = checkpoint.donnees["identifiant"]
        atelier.git_restaurer(identifiant)

        deuxieme = atelier.git_restaurer(identifiant)

        assert deuxieme.ok is False
        assert "inconnu" in deuxieme.message.lower() or "deja" in deuxieme.message.lower()

    def test_un_identifiant_inconnu_est_un_echec_nomme(self, depot):
        atelier = Atelier(racine=depot)

        resultat = atelier.git_restaurer("n-existe-pas")

        assert resultat.ok is False
