"""`isoler`/`nettoyer_worktree` — mission ARENA x TRANS4MERS §18/§52.

Un vrai dépôt git, un vrai `git worktree add`, un vrai fichier écrit DANS le
worktree isolé — jamais un double de git.
"""
import subprocess

from tools.atelier.atelier import Atelier


def _depot(dossier) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=dossier, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=dossier, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=dossier, check=True)
    (dossier / "f.txt").write_text("depart\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=dossier, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=dossier, check=True)


class TestIsolerCreeUnVraiWorktree:
    def test_le_worktree_existe_reellement_sur_le_disque(self, tmp_path):
        depot = tmp_path / "depot"
        _depot(depot)
        atelier = Atelier(racine=depot)

        resultat = atelier.isoler("correctif-x")

        assert resultat.ok, resultat.erreur or resultat.message
        chemin = resultat.donnees["chemin"]
        assert (depot / ".worktrees" / "correctif-x" / "f.txt").is_file()
        assert chemin.endswith("correctif-x")

    def test_travailler_dans_le_worktree_ne_touche_pas_l_arbre_principal(self, tmp_path):
        depot = tmp_path / "depot"
        _depot(depot)
        atelier = Atelier(racine=depot)
        cree = atelier.isoler("isole")

        # Ecrit avec le chemin ABSOLU rendu par isoler() — exactement ce que
        # Dioumtoukay ferait en CHEMIN: apres avoir lu ce resultat.
        chemin_absolu = f"{cree.donnees['chemin']}/nouveau.txt"
        ecriture = atelier.ecrire(chemin_absolu, "contenu isole")
        assert ecriture.ok, ecriture.message

        assert not (depot / "nouveau.txt").exists(), (
            "l'arbre principal ne doit jamais recevoir ce que le worktree isole a recu"
        )
        assert (depot / ".worktrees" / "isole" / "nouveau.txt").read_text(
            encoding="utf-8") == "contenu isole"

    def test_gitignore_protege_worktrees_s_il_existe_deja(self, tmp_path):
        depot = tmp_path / "depot"
        _depot(depot)
        (depot / ".gitignore").write_text("*.pyc\n", encoding="utf-8")

        Atelier(racine=depot).isoler("proteger")

        assert ".worktrees/" in (depot / ".gitignore").read_text(encoding="utf-8").splitlines()

    def test_sans_gitignore_prealable_aucun_n_est_cree(self, tmp_path):
        """Ne cree jamais un .gitignore dans un depot qui n'en a pas choisi."""
        depot = tmp_path / "depot"
        _depot(depot)

        Atelier(racine=depot).isoler("sans-gitignore")

        assert not (depot / ".gitignore").exists()

    def test_un_nom_invalide_est_refuse_proprement(self, tmp_path):
        depot = tmp_path / "depot"
        _depot(depot)

        resultat = Atelier(racine=depot).isoler("../evasion")

        assert resultat.ok is False


class TestNettoyerWorktree:
    def test_un_worktree_propre_est_retire(self, tmp_path):
        depot = tmp_path / "depot"
        _depot(depot)
        atelier = Atelier(racine=depot)
        atelier.isoler("temporaire")

        resultat = atelier.nettoyer_worktree("temporaire")

        assert resultat.ok, resultat.erreur or resultat.message
        assert not (depot / ".worktrees" / "temporaire").exists()

    def test_un_worktree_avec_du_travail_non_commite_n_est_pas_efface(self, tmp_path):
        """Mission §19 : never destroy user work. Rien ne force ici."""
        depot = tmp_path / "depot"
        _depot(depot)
        atelier = Atelier(racine=depot)
        atelier.isoler("precieux")
        (depot / ".worktrees" / "precieux" / "pas_sauvegarde.txt").write_text(
            "travail non commite", encoding="utf-8")

        resultat = atelier.nettoyer_worktree("precieux")

        assert resultat.ok is False, "git doit refuser, pas ecraser le travail non commite"
        assert (depot / ".worktrees" / "precieux" / "pas_sauvegarde.txt").is_file(), (
            "le fichier non commite doit survivre au nettoyage refuse"
        )
