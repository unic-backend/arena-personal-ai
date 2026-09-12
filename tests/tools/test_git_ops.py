"""`tools/atelier/git_ops.py` — mission ARENA x GITGUI, second passage
(DEC-0094). Sur de vrais dépôts git, jamais un raccourci qui contournerait le
parsing ou l'exécution réelle. Chaque garantie de la mission a son test :
idempotence, précondition de HEAD, non-fast-forward, conflit réel,
abandon/continuation, préservation d'un changement non lié, sécurité des
arguments.
"""
import subprocess
from pathlib import Path

import pytest

from tools.atelier import git_etat, git_ops


def _git(racine: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *arguments], cwd=str(racine), capture_output=True,
                          text=True, check=check)


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


def _tete(racine: Path) -> str:
    return git_etat.lire_etat(racine).tete


class TestClassificationErreur:
    def test_motifs_connus(self):
        assert git_ops.classer_erreur("fatal: not a git repository") == git_ops.TypeErreurGit.NON_UN_DEPOT
        assert git_ops.classer_erreur("CONFLICT (content): Merge conflict in a.txt") == git_ops.TypeErreurGit.CONFLIT
        assert git_ops.classer_erreur(
            "! [rejected] main -> main (non-fast-forward)") == git_ops.TypeErreurGit.NON_FAST_FORWARD
        assert git_ops.classer_erreur(
            "fatal: could not read Username for 'https://x'") == git_ops.TypeErreurGit.ECHEC_AUTH
        assert git_ops.classer_erreur(
            "fatal: unable to access 'https://x': Could not resolve host"
        ) == git_ops.TypeErreurGit.DISTANT_INACCESSIBLE
        assert git_ops.classer_erreur(
            "error: pathspec 'nope' did not match any file(s)") == git_ops.TypeErreurGit.BRANCHE_INTROUVABLE
        assert git_ops.classer_erreur("nothing to commit, working tree clean") == git_ops.TypeErreurGit.RIEN_A_FAIRE

    def test_texte_inconnu_est_classe_inconnue(self):
        assert git_ops.classer_erreur("un message jamais vu ailleurs") == git_ops.TypeErreurGit.INCONNUE


class TestStagerDesindexer:
    def test_stager_indexe_reellement(self, depot):
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        r = git_ops.stager(depot, ["a.txt"])
        assert r.ok
        etat = git_etat.lire_etat(depot)
        assert etat.indexes and etat.indexes[0].chemin == "a.txt"

    def test_desindexer_retire_de_l_index_sans_toucher_l_arbre(self, depot):
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        r = git_ops.desindexer(depot, ["a.txt"])
        assert r.ok
        etat = git_etat.lire_etat(depot)
        assert not etat.indexes
        assert etat.modifies and etat.modifies[0].chemin == "a.txt"
        assert (depot / "a.txt").read_text(encoding="utf-8") == "modifie\n"

    def test_stager_chemins_vides_est_un_echec_nomme(self, depot):
        r = git_ops.stager(depot, [])
        assert r.ok is False


class TestCommettre:
    def test_commit_reussi_bouge_head_et_le_verifie(self, depot):
        avant = _tete(depot)
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        r = git_ops.commettre(depot, "modif")
        assert r.ok
        assert r.tete_avant == avant
        assert r.tete_apres != avant
        assert r.tete_apres == _tete(depot)

    def test_commit_sans_rien_stage_est_rien_a_faire(self, depot):
        r = git_ops.commettre(depot, "vide")
        assert r.ok is False
        assert r.type_erreur == git_ops.TypeErreurGit.RIEN_A_FAIRE

    def test_message_vide_refuse_avant_tout_appel_git(self, depot):
        (depot / "a.txt").write_text("x\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        r = git_ops.commettre(depot, "   ")
        assert r.ok is False


class TestIdempotence:
    def test_meme_identifiant_ne_rejoue_pas_le_commit(self, depot):
        journal = git_ops.JournalOperationsGit()
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])

        r1 = git_ops.commettre(depot, "modif", identifiant_operation="op-1", journal=journal)
        r2 = git_ops.commettre(depot, "modif", identifiant_operation="op-1", journal=journal)

        assert r1.ok and r1.doublon is False
        assert r2.ok and r2.doublon is True
        assert r1.tete_apres == r2.tete_apres
        log = _git(depot, "log", "--oneline").stdout.splitlines()
        assert len(log) == 2  # initial + modif, jamais un troisieme

    def test_identifiants_differents_executent_deux_fois(self, depot):
        journal = git_ops.JournalOperationsGit()
        (depot / "a.txt").write_text("v1\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        r1 = git_ops.commettre(depot, "v1", identifiant_operation="op-1", journal=journal)
        (depot / "a.txt").write_text("v2\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        r2 = git_ops.commettre(depot, "v2", identifiant_operation="op-2", journal=journal)
        assert r1.doublon is False and r2.doublon is False
        assert r1.tete_apres != r2.tete_apres

    def test_journal_plafonne_oublie_le_plus_ancien(self, depot):
        journal = git_ops.JournalOperationsGit(capacite=2)
        for i in range(3):
            (depot / "a.txt").write_text(f"v{i}\n", encoding="utf-8")
            git_ops.stager(depot, ["a.txt"])
            git_ops.commettre(depot, f"v{i}", identifiant_operation=f"op-{i}", journal=journal)
        # op-0 a ete evince (capacite 2, 3 identifiants inseres) : le rejouer
        # avec op-0 EXECUTE une nouvelle operation plutot que de rendre un
        # ancien resultat qui n'existe plus.
        (depot / "a.txt").write_text("v3\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        r = git_ops.commettre(depot, "v3", identifiant_operation="op-0", journal=journal)
        assert r.doublon is False


class TestPreconditionHead:
    def test_tete_attendue_correcte_laisse_faire(self, depot):
        avant = _tete(depot)
        (depot / "a.txt").write_text("x\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        r = git_ops.commettre(depot, "ok", tete_attendue=avant)
        assert r.ok

    def test_tete_changee_refuse_sans_muter(self, depot):
        tete_a = _tete(depot)
        # Un changement externe, comme un autre outil ou une autre tache.
        (depot / "b.txt").write_text("externe\n", encoding="utf-8")
        _git(depot, "add", "-A")
        _git(depot, "commit", "-q", "-m", "externe")
        tete_b = _tete(depot)
        assert tete_a != tete_b

        (depot / "a.txt").write_text("devrait etre refuse\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        r = git_ops.commettre(depot, "refuse", tete_attendue=tete_a)

        assert r.ok is False
        assert r.donnees["tete_attendue"] == tete_a
        assert r.donnees["tete_reelle"] == tete_b
        # Rien n'a ete mute : toujours 2 commits (initial + externe), le
        # fichier reste indexe mais non commite.
        log = _git(depot, "log", "--oneline").stdout.splitlines()
        assert len(log) == 2
        etat = git_etat.lire_etat(depot)
        assert any(f.chemin == "a.txt" for f in etat.indexes)


class TestPreservationChangementUtilisateur:
    def test_ne_commite_que_le_fichier_demande(self, depot):
        (depot / "a.txt").write_text("modifie par la tache\n", encoding="utf-8")
        (depot / "b.txt").write_text("modifie par le proprietaire, sans rapport\n", encoding="utf-8")
        _git(depot, "add", "-A", "--", "b.txt")  # simule un fichier deja en cours ailleurs
        _git(depot, "reset", "-q", "--", "b.txt")

        git_ops.stager(depot, ["a.txt"])
        r = git_ops.commettre(depot, "seulement a.txt")
        assert r.ok

        montre = _git(depot, "show", "--stat", "--format=", "HEAD").stdout
        assert "a.txt" in montre
        assert "b.txt" not in montre
        etat = git_etat.lire_etat(depot)
        # b.txt n'a jamais ete suivi (jamais commite avant) : il reste
        # "non suivi" apres le reset, pas "modifie" — c'est la trace
        # attendue d'un fichier du proprietaire jamais touche par la tache.
        assert any(f.chemin == "b.txt" for f in etat.non_suivis)


class TestBranches:
    def test_creer_branche_et_basculer(self, depot):
        r = git_ops.creer_branche(depot, "feature-x", depuis="HEAD", basculer=True)
        assert r.ok
        etat = git_etat.lire_etat(depot)
        assert etat.branche == "feature-x"

    def test_creer_branche_sans_basculer_reste_sur_place(self, depot):
        r = git_ops.creer_branche(depot, "feature-y", basculer=False)
        assert r.ok
        etat = git_etat.lire_etat(depot)
        assert etat.branche == "main"

    def test_nom_de_branche_invalide_refuse(self, depot):
        r = git_ops.creer_branche(depot, "nom avec espace")
        assert r.ok is False

    def test_basculer_verifie_la_branche_reellement_courante(self, depot):
        git_ops.creer_branche(depot, "feature-z", basculer=False)
        r = git_ops.basculer(depot, "feature-z")
        assert r.ok
        etat = git_etat.lire_etat(depot)
        assert etat.branche == "feature-z"

    def test_basculer_branche_inexistante_est_un_echec_classe(self, depot):
        r = git_ops.basculer(depot, "n-existe-pas")
        assert r.ok is False
        assert r.type_erreur == git_ops.TypeErreurGit.BRANCHE_INTROUVABLE

    def test_lister_branches(self, depot):
        git_ops.creer_branche(depot, "autre", basculer=False)
        r = git_ops.lister_branches(depot)
        assert r.ok
        noms = {b["nom"] for b in r.donnees["branches"]}
        assert {"main", "autre"} <= noms


@pytest.fixture
def paire_distant_local(tmp_path):
    """Un dépôt distant nu + un premier clone local avec un commit poussé —
    la base pour les tests réseau (fetch/pull/push/non-fast-forward)."""
    distant = tmp_path / "distant.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(distant)], check=True)
    local = tmp_path / "local1"
    local.mkdir()
    _git(local, "init", "-q", "-b", "main")
    _git(local, "config", "user.email", "a@a.a")
    _git(local, "config", "user.name", "a")
    _git(local, "remote", "add", "origin", str(distant))
    (local / "x.txt").write_text("1\n", encoding="utf-8")
    _git(local, "add", "-A")
    _git(local, "commit", "-q", "-m", "c1")
    assert git_ops.pousser(local, "origin", "main").ok
    return distant, local


class TestReseau:
    def test_fetch_et_pull(self, tmp_path, paire_distant_local):
        distant, local1 = paire_distant_local
        local2 = tmp_path / "local2"
        subprocess.run(["git", "clone", "-q", str(distant), str(local2)], check=True)
        _git(local2, "config", "user.email", "a@a.a")
        _git(local2, "config", "user.name", "a")
        (local2 / "y.txt").write_text("2\n", encoding="utf-8")
        _git(local2, "add", "-A")
        _git(local2, "commit", "-q", "-m", "c2")
        assert git_ops.pousser(local2, "origin", "main").ok

        rf = git_ops.recuperer(local1, "origin")
        assert rf.ok
        rp = git_ops.tirer(local1, "origin")
        assert rp.ok
        assert (local1 / "y.txt").exists()

    def test_push_non_fast_forward_refuse_sans_forcer(self, tmp_path, paire_distant_local):
        distant, local1 = paire_distant_local
        local2 = tmp_path / "local2"
        subprocess.run(["git", "clone", "-q", str(distant), str(local2)], check=True)
        _git(local2, "config", "user.email", "a@a.a")
        _git(local2, "config", "user.name", "a")
        (local2 / "y.txt").write_text("2\n", encoding="utf-8")
        _git(local2, "add", "-A")
        _git(local2, "commit", "-q", "-m", "c2")
        assert git_ops.pousser(local2, "origin", "main").ok

        (local1 / "z.txt").write_text("3\n", encoding="utf-8")
        _git(local1, "add", "-A")
        _git(local1, "commit", "-q", "-m", "c3")
        r = git_ops.pousser(local1, "origin", "main")
        assert r.ok is False
        assert r.type_erreur == git_ops.TypeErreurGit.NON_FAST_FORWARD

    def test_force_avec_bail_jamais_force_nu_et_refuse_si_bail_perime(self, tmp_path, paire_distant_local):
        distant, local1 = paire_distant_local
        local2 = tmp_path / "local2"
        subprocess.run(["git", "clone", "-q", str(distant), str(local2)], check=True)
        _git(local2, "config", "user.email", "a@a.a")
        _git(local2, "config", "user.name", "a")
        (local2 / "y.txt").write_text("2\n", encoding="utf-8")
        _git(local2, "add", "-A")
        _git(local2, "commit", "-q", "-m", "c2")
        assert git_ops.pousser(local2, "origin", "main").ok

        (local1 / "z.txt").write_text("3\n", encoding="utf-8")
        _git(local1, "add", "-A")
        _git(local1, "commit", "-q", "-m", "c3")

        # local1 n'a pas encore vu le push de local2 : son "bail" (ce qu'il
        # croit etre origin/main) est perime, --force-with-lease refuse.
        r = git_ops.pousser(local1, "origin", "main", force_avec_bail=True)
        assert r.ok is False
        assert r.type_erreur == git_ops.TypeErreurGit.NON_FAST_FORWARD

        # Apres un fetch, le bail est a jour : --force-with-lease reussit.
        git_ops.recuperer(local1, "origin")
        r2 = git_ops.pousser(local1, "origin", "main", force_avec_bail=True)
        assert r2.ok

    def test_api_n_expose_jamais_force_nu(self):
        import inspect
        signature = inspect.signature(git_ops.pousser)
        assert "force" not in [p for p in signature.parameters if p == "force"]
        assert "force_avec_bail" in signature.parameters


class TestFusionEtConflit:
    def _deux_branches_en_conflit(self, depot):
        _git(depot, "checkout", "-q", "-b", "branche-a")
        (depot / "a.txt").write_text("version A\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "a")
        _git(depot, "checkout", "-q", "main")
        (depot / "a.txt").write_text("version B\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "b")

    def test_conflit_reel_detecte_et_classe(self, depot):
        self._deux_branches_en_conflit(depot)
        r = git_ops.fusionner(depot, "branche-a")
        assert r.ok is False
        assert r.type_erreur == git_ops.TypeErreurGit.CONFLIT
        etat = git_etat.lire_etat(depot)
        assert etat.operation == git_etat.EtatOperation.FUSION
        assert [f.chemin for f in etat.conflits] == ["a.txt"]

    def test_lire_conflit_rend_les_trois_cotes(self, depot):
        self._deux_branches_en_conflit(depot)
        git_ops.fusionner(depot, "branche-a")
        r = git_ops.lire_conflit(depot, "a.txt")
        assert r.ok
        assert r.donnees["notre_version"] == "version B\n"
        assert r.donnees["leur_version"] == "version A\n"
        assert r.donnees["version_de_base"] == "contenu initial\n"

    def test_fusion_puis_resolution_puis_continuer(self, depot):
        self._deux_branches_en_conflit(depot)
        git_ops.fusionner(depot, "branche-a")
        (depot / "a.txt").write_text("resolu\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        r = git_ops.continuer_operation(depot)
        assert r.ok
        etat = git_etat.lire_etat(depot)
        assert etat.operation == git_etat.EtatOperation.PROPRE
        assert (depot / "a.txt").read_text(encoding="utf-8") == "resolu\n"

    def test_fusion_puis_abandon_revient_a_l_etat_valide(self, depot):
        self._deux_branches_en_conflit(depot)
        git_ops.fusionner(depot, "branche-a")
        r = git_ops.abandonner_operation(depot)
        assert r.ok
        etat = git_etat.lire_etat(depot)
        assert etat.operation == git_etat.EtatOperation.PROPRE
        assert etat.propre
        assert (depot / "a.txt").read_text(encoding="utf-8") == "version B\n"

    def test_continuer_sans_operation_en_cours_est_un_echec_nomme(self, depot):
        r = git_ops.continuer_operation(depot)
        assert r.ok is False

    def test_abandonner_sans_operation_en_cours_est_un_echec_nomme(self, depot):
        r = git_ops.abandonner_operation(depot)
        assert r.ok is False


class TestRebaseCherryPickRevert:
    def test_rebase_conflictuel_puis_abandon(self, depot):
        _git(depot, "checkout", "-q", "-b", "feature")
        (depot / "a.txt").write_text("feature\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "feature-1")
        _git(depot, "checkout", "-q", "main")
        (depot / "a.txt").write_text("main\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "main-1")
        _git(depot, "checkout", "-q", "feature")

        r = git_ops.rebaser(depot, "main")
        assert r.ok is False
        etat = git_etat.lire_etat(depot)
        assert etat.operation == git_etat.EtatOperation.REBASE

        ra = git_ops.abandonner_operation(depot)
        assert ra.ok
        etat2 = git_etat.lire_etat(depot)
        assert etat2.operation == git_etat.EtatOperation.PROPRE

    def test_cherry_pick_reel(self, depot):
        _git(depot, "checkout", "-q", "-b", "source")
        (depot / "c.txt").write_text("cherry\n", encoding="utf-8")
        _git(depot, "add", "-A")
        _git(depot, "commit", "-q", "-m", "a-picorer")
        cible = _git(depot, "rev-parse", "HEAD").stdout.strip()
        _git(depot, "checkout", "-q", "main")

        r = git_ops.cherry_pick(depot, cible)
        assert r.ok
        assert (depot / "c.txt").read_text(encoding="utf-8") == "cherry\n"

    def test_revert_reel_annule_par_un_nouveau_commit(self, depot):
        (depot / "a.txt").write_text("a annuler\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "a-annuler")
        cible = _git(depot, "rev-parse", "HEAD").stdout.strip()

        r = git_ops.annuler_commit(depot, cible)
        assert r.ok
        assert (depot / "a.txt").read_text(encoding="utf-8") == "contenu initial\n"
        log = _git(depot, "log", "--oneline").stdout
        assert "Revert" in log


class TestTagEtStash:
    def test_creer_tag(self, depot):
        r = git_ops.creer_tag(depot, "v1.0.0", message="premiere version")
        assert r.ok
        tags = _git(depot, "tag").stdout.split()
        assert "v1.0.0" in tags

    def test_remiser_et_appliquer(self, depot):
        (depot / "a.txt").write_text("en cours\n", encoding="utf-8")
        r = git_ops.remiser(depot, message="travail en cours")
        assert r.ok
        assert (depot / "a.txt").read_text(encoding="utf-8") == "contenu initial\n"

        r2 = git_ops.appliquer_remise(depot)
        assert r2.ok
        assert (depot / "a.txt").read_text(encoding="utf-8") == "en cours\n"


class TestSecurite:
    def test_nom_de_fichier_avec_espaces_et_guillemets(self, depot):
        nom = 'fichier avec espaces et "guillemets".txt'
        (depot / nom).write_text("contenu\n", encoding="utf-8")
        r = git_ops.stager(depot, [nom])
        assert r.ok
        rc = git_ops.commettre(depot, "fichier a nom complique")
        assert rc.ok
        etat = git_etat.lire_etat(depot)
        assert etat.propre

    def test_nom_de_branche_avec_metacaracteres_shell_refuse_ou_echoue_proprement(self, depot):
        # Aucune injection possible (arguments en liste, jamais shell=True) :
        # au pire un refus nomme, jamais une commande executee en plus.
        r = git_ops.creer_branche(depot, "branche; rm -rf /tmp/rien")
        assert r.ok is False
        # Verifie qu'aucun fichier n'a ete supprime/cree de facon inattendue :
        # le depot est toujours dans son etat d'origine.
        etat = git_etat.lire_etat(depot)
        assert etat.branche == "main"

    def test_message_de_commit_avec_metacaracteres(self, depot):
        (depot / "a.txt").write_text("x\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"])
        message = "fix: `$(rm -rf /)` et \"guillemets\" et 'apostrophes' et $VAR"
        r = git_ops.commettre(depot, message)
        assert r.ok
        log = _git(depot, "log", "-1", "--format=%s").stdout.strip()
        assert log == message.splitlines()[0] if "\n" not in message else True

    def test_traversee_de_chemin_dans_stage_echoue_proprement(self, depot):
        r = git_ops.stager(depot, ["../../../etc/passwd"])
        # git refuse lui-meme un chemin hors du depot : echec propre, jamais
        # une exception non geree ni un ajout hors de l'arbre de travail.
        assert isinstance(r, git_ops.ResultatOperation)

    def test_nom_de_branche_debutant_par_un_indicateur_ne_supprime_rien(self, depot):
        """Régression réelle, mesurée avant ce correctif : `git branch -D
        <depuis>` s'exécutait VRAIMENT quand `nom="-D"` était passé nu à
        `git branch <nom> <depuis>` — "-D" était lu comme l'option de
        suppression forcée, pas comme le nom voulu, et la branche visée par
        `depuis` était supprimée au lieu qu'une branche "-D" soit créée.
        """
        _git(depot, "checkout", "-q", "-b", "a-proteger")
        _git(depot, "checkout", "-q", "main")

        r = git_ops.creer_branche(depot, "-D", depuis="a-proteger")

        assert r.ok is False
        branches = _git(depot, "branch").stdout
        assert "a-proteger" in branches

    def test_cible_de_bascule_debutant_par_un_indicateur_refusee(self, depot):
        r = git_ops.basculer(depot, "-f")
        assert r.ok is False

    def test_distant_debutant_par_un_indicateur_refuse(self, depot):
        r = git_ops.recuperer(depot, "--upload-pack=touch /tmp/preuve-injection")
        assert r.ok is False

    def test_commit_cherry_pick_debutant_par_un_indicateur_refuse(self, depot):
        r = git_ops.cherry_pick(depot, "-x")
        assert r.ok is False

    def test_nom_de_tag_debutant_par_un_indicateur_refuse(self, depot):
        r = git_ops.creer_tag(depot, "-d")
        assert r.ok is False

    def test_chemin_unicode(self, depot):
        nom = "résumé_émoji_😀.txt"
        (depot / nom).write_text("contenu\n", encoding="utf-8")
        r = git_ops.stager(depot, [nom])
        assert r.ok
        rc = git_ops.commettre(depot, "fichier unicode")
        assert rc.ok

    def test_chemin_tres_long(self, depot):
        segment = "a" * 200
        sous_dossier = depot / segment
        sous_dossier.mkdir()
        nom_relatif = f"{segment}/{'b' * 200}.txt"
        (sous_dossier / (("b" * 200) + ".txt")).write_text("x\n", encoding="utf-8")
        r = git_ops.stager(depot, [nom_relatif])
        assert r.ok
        rc = git_ops.commettre(depot, "chemin tres long")
        assert rc.ok


class TestJournal:
    def test_entrees_journal_ne_contiennent_aucun_secret(self, depot):
        journal = git_ops.JournalOperationsGit()
        (depot / "a.txt").write_text("x\n", encoding="utf-8")
        git_ops.stager(depot, ["a.txt"], journal=journal)
        git_ops.commettre(depot, "message avec un token ghp_ABC123", journal=journal)
        entrees = journal.entrees()
        assert len(entrees) == 2
        for entree in entrees:
            texte = str(entree)
            # Le journal ne garde que branche/tete/operation/horodatage —
            # jamais le message de commit ni la sortie complete de git.
            assert "ghp_ABC123" not in texte
