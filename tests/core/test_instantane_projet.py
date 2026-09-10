"""`core/context/instantane_projet.py` — mission ARENA x OPENCONTEXT
(DEC prochain, 10/09/2026).

Ce module ne lit que des fichiers réels : chaque test construit un petit
dépôt de test (jamais le vrai dépôt d'ARENA, dont le contenu changerait
sous les pieds du test) et vérifie ce qui est réellement rendu.
"""
import subprocess
from pathlib import Path

from core.context.instantane_projet import (
    BUDGET_CARACTERES_MAX,
    FraicheurFichier,
    instantane,
)


def _git(racine: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=racine, check=True, capture_output=True)


def _depot_git(tmp_path: Path, date_commit: str) -> Path:
    """Un dépôt git réel, avec un commit initial daté — jamais une simulation
    du format de sortie de `git log`."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("depot de test\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    env_commit = ["commit", "-q", "-m", "init",
                  f"--date={date_commit}T00:00:00"]
    subprocess.run(
        ["git", *env_commit], cwd=tmp_path, check=True, capture_output=True,
        env={"GIT_AUTHOR_DATE": f"{date_commit}T00:00:00",
             "GIT_COMMITTER_DATE": f"{date_commit}T00:00:00",
             "PATH": "/usr/bin:/bin"})
    return tmp_path


class TestDepotVide:
    def test_aucun_fichier_suivi_rend_un_instantane_vide(self, tmp_path):
        resultat = instantane(tmp_path)

        assert resultat.vide
        assert resultat.texte == ""
        assert resultat.fraicheurs == []


class TestContenuAssemble:
    def test_les_deux_fichiers_suivis_apparaissent(self, tmp_path):
        memoire = tmp_path / "PROJECT_MEMORY"
        memoire.mkdir()
        (memoire / "PROJECT_MAP.md").write_text(
            "# CARTE\n\n*Mise à jour : 2026-01-01.*\ncontenu carte", encoding="utf-8")
        (memoire / "LOCKED_ZONES.md").write_text(
            "# ZONES\n\n*Mise à jour : 2026-01-01.*\ncontenu zones", encoding="utf-8")

        resultat = instantane(tmp_path)

        assert not resultat.vide
        assert "contenu carte" in resultat.texte
        assert "contenu zones" in resultat.texte
        # Zones verrouillées d'abord (FICHIERS_SUIVIS) : le plus critique ne
        # doit jamais être coupé par un budget avant d'avoir été vu.
        assert resultat.texte.index("contenu zones") < resultat.texte.index("contenu carte")

    def test_un_seul_fichier_present_n_empeche_pas_l_autre(self, tmp_path):
        memoire = tmp_path / "PROJECT_MEMORY"
        memoire.mkdir()
        (memoire / "PROJECT_MAP.md").write_text(
            "*Mise à jour : 2026-01-01.*\nseule la carte existe", encoding="utf-8")

        resultat = instantane(tmp_path)

        assert "seule la carte existe" in resultat.texte
        assert len(resultat.fraicheurs) == 1


class TestFraicheur:
    def test_aucune_date_declaree(self, tmp_path):
        memoire = tmp_path / "PROJECT_MEMORY"
        memoire.mkdir()
        (memoire / "LOCKED_ZONES.md").write_text("pas de date ici", encoding="utf-8")

        resultat = instantane(tmp_path)

        assert resultat.fraicheurs[0].date_declaree is None
        assert "aucune date déclarée" in resultat.fraicheurs[0].bandeau()
        assert resultat.fraicheurs[0].perime is False

    def test_date_declaree_sans_depot_git(self, tmp_path):
        memoire = tmp_path / "PROJECT_MEMORY"
        memoire.mkdir()
        (memoire / "LOCKED_ZONES.md").write_text(
            "*Mise à jour : 2026-01-01.*\n", encoding="utf-8")

        resultat = instantane(tmp_path)

        f = resultat.fraicheurs[0]
        assert f.date_declaree == "2026-01-01"
        assert f.commits_depuis is None
        assert "dépôt git indisponible" in f.bandeau()
        assert f.perime is False  # None n'est jamais confondu avec périmé

    def test_a_jour_zero_commit_depuis(self, tmp_path):
        _depot_git(tmp_path, "2026-06-01")
        memoire = tmp_path / "PROJECT_MEMORY"
        memoire.mkdir()
        (memoire / "LOCKED_ZONES.md").write_text(
            "*Mise à jour : 2026-06-01.*\n", encoding="utf-8")

        resultat = instantane(tmp_path)

        f = resultat.fraicheurs[0]
        assert f.commits_depuis == 0
        assert f.perime is False
        assert "à jour" in f.bandeau()

    def test_perime_des_commits_reels_apres_la_date_declaree(self, tmp_path):
        _depot_git(tmp_path, "2026-01-01")
        memoire = tmp_path / "PROJECT_MEMORY"
        memoire.mkdir()
        (memoire / "LOCKED_ZONES.md").write_text(
            "*Mise à jour : 2026-01-01.*\n", encoding="utf-8")
        # Un second commit, réel, daté après la date déclarée du fichier.
        (tmp_path / "autre.txt").write_text("x", encoding="utf-8")
        _git(tmp_path, "add", ".")
        subprocess.run(
            ["git", "commit", "-q", "-m", "second"], cwd=tmp_path,
            check=True, capture_output=True,
            env={"GIT_AUTHOR_DATE": "2026-06-01T00:00:00",
                 "GIT_COMMITTER_DATE": "2026-06-01T00:00:00",
                 "PATH": "/usr/bin:/bin"})

        resultat = instantane(tmp_path)

        f = resultat.fraicheurs[0]
        assert f.commits_depuis == 1
        assert f.perime is True
        assert "peut-être périmé" in f.bandeau()
        assert "1 commit" in f.bandeau()  # jamais "1 commits"


class TestDecisionsRecentes:
    def test_seuls_les_titres_sont_repris_jamais_le_corps(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "DECISIONS.md").write_text(
            "## DEC-0001 — Première décision\n\nCorps secret jamais repris ici.\n\n"
            "## DEC-0002 — Deuxième décision\n\nAutre corps.\n",
            encoding="utf-8")
        (tmp_path / "PROJECT_MEMORY").mkdir()
        (tmp_path / "PROJECT_MEMORY" / "PROJECT_MAP.md").write_text(
            "*Mise à jour : 2026-01-01.*\ncarte", encoding="utf-8")

        resultat = instantane(tmp_path)

        assert "DEC-0002" in resultat.texte
        assert "DEC-0001" in resultat.texte
        assert "Corps secret jamais repris ici" not in resultat.texte
        # La plus récente en premier.
        assert resultat.texte.index("DEC-0002") < resultat.texte.index("DEC-0001")

    def test_plus_de_decisions_que_le_maximum_garde_seulement_les_recentes(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        corps = "\n\n".join(f"## DEC-{i:04d} — Décision {i}\n\ncorps" for i in range(1, 15))
        (docs / "DECISIONS.md").write_text(corps, encoding="utf-8")
        (tmp_path / "PROJECT_MEMORY").mkdir()
        (tmp_path / "PROJECT_MEMORY" / "PROJECT_MAP.md").write_text(
            "*Mise à jour : 2026-01-01.*\ncarte", encoding="utf-8")

        resultat = instantane(tmp_path)

        assert "DEC-0014" in resultat.texte  # la plus récente
        assert "DEC-0001" not in resultat.texte  # hors des 8 dernières

    def test_sans_decisions_md_rien_ne_casse(self, tmp_path):
        (tmp_path / "PROJECT_MEMORY").mkdir()
        (tmp_path / "PROJECT_MEMORY" / "PROJECT_MAP.md").write_text(
            "*Mise à jour : 2026-01-01.*\ncarte", encoding="utf-8")

        resultat = instantane(tmp_path)

        assert not resultat.vide
        assert "Décisions récentes" not in resultat.texte


class TestBudget:
    def test_un_contenu_trop_long_est_tronque_avec_un_avis(self, tmp_path):
        memoire = tmp_path / "PROJECT_MEMORY"
        memoire.mkdir()
        (memoire / "PROJECT_MAP.md").write_text(
            "*Mise à jour : 2026-01-01.*\n" + ("x" * (BUDGET_CARACTERES_MAX * 2)),
            encoding="utf-8")

        resultat = instantane(tmp_path)

        assert resultat.tronque is True
        assert "tronqué" in resultat.texte
        assert len(resultat.texte) < BUDGET_CARACTERES_MAX * 2

    def test_un_contenu_sous_le_budget_n_est_pas_tronque(self, tmp_path):
        memoire = tmp_path / "PROJECT_MEMORY"
        memoire.mkdir()
        (memoire / "PROJECT_MAP.md").write_text(
            "*Mise à jour : 2026-01-01.*\ncourt", encoding="utf-8")

        resultat = instantane(tmp_path)

        assert resultat.tronque is False
        assert "tronqué" not in resultat.texte


class TestFraicheurFichierDataclass:
    def test_bandeau_sans_date(self):
        f = FraicheurFichier(chemin="x.md", date_declaree=None, commits_depuis=None)
        assert f.perime is False
        assert "aucune date déclarée" in f.bandeau()
