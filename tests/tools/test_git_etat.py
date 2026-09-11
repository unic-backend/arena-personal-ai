"""État Git structuré (DEC-0093, mission ARENA x GITGUI) — sur de vrais
dépôts git, jamais une simulation.

Chaque test construit un dépôt réel dans `tmp_path`, exécute de vraies
commandes git pour produire l'état à mesurer (fichier modifié, indexé, non
suivi, supprimé, conflit réel, HEAD détachée, rebase en cours), puis vérifie
que `lire_etat()`/`lire_diff()`/`creer_checkpoint()`/`restaurer_checkpoint()`
le lisent correctement.
"""
import subprocess
from pathlib import Path

import pytest

from tools.atelier.git_etat import (
    BRANCHES_PROTEGEES_PAR_DEFAUT,
    EtatOperation,
    StatutFichier,
    creer_checkpoint,
    fichiers_touches_depuis,
    lire_diff,
    lire_etat,
    restaurer_checkpoint,
)


def _git(racine: Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *arguments], cwd=str(racine), capture_output=True,
                          text=True, check=True)


@pytest.fixture
def depot(tmp_path) -> Path:
    racine = tmp_path / "depot"
    racine.mkdir()
    _git(racine, "init", "-q")
    _git(racine, "config", "user.email", "test@test.local")
    _git(racine, "config", "user.name", "test")
    return racine


def _commit_initial(racine: Path, *fichiers: str) -> None:
    for nom in fichiers:
        (racine / nom).write_text("contenu initial\n", encoding="utf-8")
    _git(racine, "add", "-A")
    _git(racine, "commit", "-q", "-m", "initial")


class TestLireEtatDepotPropre:
    def test_un_depot_propre_juste_apres_un_commit(self, depot):
        _commit_initial(depot, "a.txt")

        etat = lire_etat(depot)

        assert etat.branche in ("master", "main")
        assert etat.detachee is False
        assert etat.tete is not None
        assert etat.propre is True
        assert etat.operation is EtatOperation.PROPRE


class TestLireEtatFichiersMelanges:
    def test_modifie_supprime_indexe_non_suivi_dans_le_meme_depot(self, depot):
        _commit_initial(depot, "a.txt", "b.txt")
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        (depot / "b.txt").unlink()
        (depot / "c.txt").write_text("nouveau\n", encoding="utf-8")
        (depot / "d.txt").write_text("indexe\n", encoding="utf-8")
        _git(depot, "add", "d.txt")

        etat = lire_etat(depot)

        assert {f.chemin for f in etat.modifies} == {"a.txt", "b.txt"}
        assert next(f for f in etat.modifies if f.chemin == "a.txt").statut == StatutFichier.MODIFIE
        assert next(f for f in etat.modifies if f.chemin == "b.txt").statut == StatutFichier.SUPPRIME
        assert {f.chemin for f in etat.indexes} == {"d.txt"}
        assert etat.indexes[0].statut == StatutFichier.AJOUTE
        assert {f.chemin for f in etat.non_suivis} == {"c.txt"}
        assert etat.propre is False

    def test_fichiers_avec_espaces_dans_le_nom(self, depot):
        """La ligne `1 <XY> ... <chemin>` porte le chemin en dernier champ —
        des espaces dedans ne doivent pas casser le decoupage."""
        _commit_initial(depot, "base.txt")
        (depot / "nom avec espaces.txt").write_text("x\n", encoding="utf-8")
        _git(depot, "add", "nom avec espaces.txt")

        etat = lire_etat(depot)

        assert {f.chemin for f in etat.indexes} == {"nom avec espaces.txt"}


class TestBrancheEtAmont:
    def test_ahead_et_behind_par_rapport_a_l_amont(self, depot):
        _commit_initial(depot, "a.txt")
        _git(depot, "branch", "amont")
        (depot / "b.txt").write_text("x\n", encoding="utf-8")
        _git(depot, "add", "-A")
        _git(depot, "commit", "-q", "-m", "en avance")
        _git(depot, "branch", "--set-upstream-to=amont")

        etat = lire_etat(depot)

        assert etat.amont == "amont"
        assert etat.en_avance == 1
        assert etat.en_retard == 0

    def test_sans_amont_configure(self, depot):
        _commit_initial(depot, "a.txt")

        etat = lire_etat(depot)

        assert etat.amont is None
        assert etat.en_avance == 0 and etat.en_retard == 0


class TestBrancheProtegee:
    def test_main_et_master_sont_protegees_par_defaut(self, depot):
        _commit_initial(depot, "a.txt")

        etat = lire_etat(depot)

        assert etat.branche in BRANCHES_PROTEGEES_PAR_DEFAUT
        assert etat.branche_protegee() is True

    def test_une_branche_de_travail_ne_l_est_pas(self, depot):
        _commit_initial(depot, "a.txt")
        _git(depot, "checkout", "-q", "-b", "correctif-toiture")

        etat = lire_etat(depot)

        assert etat.branche_protegee() is False

    def test_ensemble_de_branches_protegees_personnalisable(self, depot):
        _commit_initial(depot, "a.txt")
        _git(depot, "checkout", "-q", "-b", "production")

        etat = lire_etat(depot)

        assert etat.branche_protegee(frozenset({"production"})) is True
        assert etat.branche_protegee(frozenset({"main"})) is False


class TestHeadDetachee:
    def test_une_tete_detachee_est_reconnue(self, depot):
        _commit_initial(depot, "a.txt")
        premier = _git(depot, "rev-parse", "HEAD").stdout.strip()
        (depot / "b.txt").write_text("x\n", encoding="utf-8")
        _git(depot, "add", "-A")
        _git(depot, "commit", "-q", "-m", "second")
        _git(depot, "checkout", "-q", premier)

        etat = lire_etat(depot)

        assert etat.detachee is True
        assert etat.branche is None


class TestConflitReel:
    def test_un_vrai_conflit_de_fusion_est_detecte(self, depot):
        _commit_initial(depot, "x.txt")
        _git(depot, "checkout", "-q", "-b", "branche_a")
        (depot / "x.txt").write_text("version A\n", encoding="utf-8")
        _git(depot, "add", "-A")
        _git(depot, "commit", "-q", "-m", "A")
        _git(depot, "checkout", "-q", "-")
        (depot / "x.txt").write_text("version master\n", encoding="utf-8")
        _git(depot, "add", "-A")
        _git(depot, "commit", "-q", "-m", "master")
        subprocess.run(["git", "merge", "branche_a", "-q"], cwd=str(depot),
                       capture_output=True, check=False)

        etat = lire_etat(depot)

        assert {f.chemin for f in etat.conflits} == {"x.txt"}
        assert etat.operation is EtatOperation.FUSION


class TestOperationEnCours:
    def test_un_rebase_en_cours_est_detecte(self, depot):
        _commit_initial(depot, "x.txt")
        _git(depot, "checkout", "-q", "-b", "branche_b")
        (depot / "x.txt").write_text("version B\n", encoding="utf-8")
        _git(depot, "add", "-A")
        _git(depot, "commit", "-q", "-m", "B")
        _git(depot, "checkout", "-q", "-")
        (depot / "x.txt").write_text("version master\n", encoding="utf-8")
        _git(depot, "add", "-A")
        _git(depot, "commit", "-q", "-m", "master")
        subprocess.run(["git", "rebase", "branche_b"], cwd=str(depot), capture_output=True, check=False)

        etat = lire_etat(depot)

        assert etat.operation is EtatOperation.REBASE


class TestLireDiff:
    def test_diff_du_travail_contient_le_vrai_texte(self, depot):
        _commit_initial(depot, "a.txt")
        (depot / "a.txt").write_text("contenu initial\nligne ajoutee\n", encoding="utf-8")

        diffs = lire_diff(depot, cible="travail")

        assert len(diffs) == 1
        assert diffs[0].chemin == "a.txt"
        assert diffs[0].statut == StatutFichier.MODIFIE
        assert "+ligne ajoutee" in diffs[0].texte

    def test_diff_de_l_index_seulement(self, depot):
        _commit_initial(depot, "a.txt")
        (depot / "nouveau.txt").write_text("x\n", encoding="utf-8")
        _git(depot, "add", "nouveau.txt")
        (depot / "a.txt").write_text("modifie non indexe\n", encoding="utf-8")

        diffs_index = lire_diff(depot, cible="index")
        diffs_travail = lire_diff(depot, cible="travail")

        assert {d.chemin for d in diffs_index} == {"nouveau.txt"}
        assert diffs_index[0].statut == StatutFichier.AJOUTE
        assert {d.chemin for d in diffs_travail} == {"a.txt"}

    def test_diff_d_un_commit_precis(self, depot):
        _commit_initial(depot, "a.txt")
        (depot / "a.txt").write_text("v2\n", encoding="utf-8")
        _git(depot, "add", "-A")
        _git(depot, "commit", "-q", "-m", "v2")
        sha = _git(depot, "rev-parse", "HEAD").stdout.strip()

        diffs = lire_diff(depot, cible=sha)

        assert diffs[0].chemin == "a.txt"

    def test_diff_limite_a_des_chemins_precis(self, depot):
        _commit_initial(depot, "a.txt", "b.txt")
        (depot / "a.txt").write_text("modif a\n", encoding="utf-8")
        (depot / "b.txt").write_text("modif b\n", encoding="utf-8")

        diffs = lire_diff(depot, cible="travail", chemins=["a.txt"])

        assert {d.chemin for d in diffs} == {"a.txt"}


class TestCheckpointEtRestauration:
    """Le cœur de la mission : ne jamais écraser un travail préexistant."""

    def test_un_fichier_cree_apres_le_checkpoint_est_efface_a_la_restauration(self, depot):
        _commit_initial(depot, "a.txt")
        checkpoint = creer_checkpoint(depot)

        (depot / "cree_par_agent.txt").write_text("x\n", encoding="utf-8")

        touches = fichiers_touches_depuis(checkpoint)
        assert touches == ["cree_par_agent.txt"]

        resultat = restaurer_checkpoint(checkpoint)

        assert resultat.ok
        assert resultat.restaures == ["cree_par_agent.txt"]
        assert not (depot / "cree_par_agent.txt").exists()

    def test_un_fichier_modifie_apres_le_checkpoint_retrouve_le_contenu_de_head(self, depot):
        _commit_initial(depot, "a.txt")
        checkpoint = creer_checkpoint(depot)

        (depot / "a.txt").write_text("modifie par agent\n", encoding="utf-8")

        resultat = restaurer_checkpoint(checkpoint)

        assert resultat.ok
        assert (depot / "a.txt").read_text(encoding="utf-8") == "contenu initial\n"

    def test_un_fichier_supprime_apres_le_checkpoint_est_recree(self, depot):
        _commit_initial(depot, "a.txt")
        checkpoint = creer_checkpoint(depot)

        (depot / "a.txt").unlink()

        resultat = restaurer_checkpoint(checkpoint)

        assert resultat.ok
        assert (depot / "a.txt").read_text(encoding="utf-8") == "contenu initial\n"

    def test_un_fichier_deja_dirty_au_checkpoint_n_est_jamais_touche(self, depot):
        """LA garantie de sécurité : le travail du propriétaire, déjà en
        cours avant le checkpoint, ne doit jamais être écrasé — même si
        l'agent modifie encore ce même fichier ensuite."""
        _commit_initial(depot, "preexistant.txt")
        (depot / "preexistant.txt").write_text("modif du proprietaire\n", encoding="utf-8")
        checkpoint = creer_checkpoint(depot)
        assert checkpoint.fichiers_preexistants == frozenset({"preexistant.txt"})

        # L'agent modifie ENCORE le meme fichier apres le checkpoint.
        (depot / "preexistant.txt").write_text("modif du proprietaire\nmodif agent\n",
                                                encoding="utf-8")

        touches = fichiers_touches_depuis(checkpoint)
        assert touches == [], "un fichier deja dirty au checkpoint ne doit jamais etre 'touche'"

        resultat = restaurer_checkpoint(checkpoint)

        assert resultat.restaures == []
        assert resultat.ignores_deja_dirty == ["preexistant.txt"]
        # Le contenu n'a PAS ete efface — ni la part du proprietaire, ni celle
        # de l'agent : aucune restauration surgicale n'est tentee ici.
        assert (depot / "preexistant.txt").read_text(encoding="utf-8") == (
            "modif du proprietaire\nmodif agent\n")

    def test_fichiers_non_touches_survivent_intacts(self, depot):
        _commit_initial(depot, "a.txt", "intact.txt")
        checkpoint = creer_checkpoint(depot)

        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")

        restaurer_checkpoint(checkpoint)

        assert (depot / "intact.txt").read_text(encoding="utf-8") == "contenu initial\n"

    def test_melange_realiste_seuls_les_ajouts_de_l_agent_disparaissent(self, depot):
        """Scenario complet : un fichier deja modifie par le proprietaire,
        un fichier intact, et deux changements de l'agent (un nouveau
        fichier, une modification d'un fichier intact)."""
        _commit_initial(depot, "deja_modifie.txt", "intact.txt", "sera_modifie.txt")
        (depot / "deja_modifie.txt").write_text("proprietaire\n", encoding="utf-8")
        checkpoint = creer_checkpoint(depot)

        (depot / "nouveau_agent.txt").write_text("x\n", encoding="utf-8")
        (depot / "sera_modifie.txt").write_text("modifie par agent\n", encoding="utf-8")

        resultat = restaurer_checkpoint(checkpoint)

        assert set(resultat.restaures) == {"nouveau_agent.txt", "sera_modifie.txt"}
        assert not (depot / "nouveau_agent.txt").exists()
        assert (depot / "sera_modifie.txt").read_text(encoding="utf-8") == "contenu initial\n"
        assert (depot / "deja_modifie.txt").read_text(encoding="utf-8") == "proprietaire\n"
        assert (depot / "intact.txt").read_text(encoding="utf-8") == "contenu initial\n"


class TestErreursReelles:
    def test_un_dossier_sans_depot_git_leve_une_erreur_nommee(self, tmp_path):
        from tools.atelier.git_etat import ErreurGit
        pas_un_depot = tmp_path / "pas_un_depot"
        pas_un_depot.mkdir()

        with pytest.raises(ErreurGit):
            lire_etat(pas_un_depot)
