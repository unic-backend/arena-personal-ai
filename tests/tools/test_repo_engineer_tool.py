"""L'outil de dépôt : ce qu'il valide, et ce qu'il refuse d'écrire.

Ce module n'avait **aucun test**, et c'est là que le défaut vivait : mesuré le
31/08/2026, `run_tests()` lançait `unittest discover`, qui ne collecte aucun
test de ce dépôt (ils sont écrits pour pytest). Il rendait donc
`success: True` après « Ran 0 tests » — une validation qui ne validait rien,
lue par un agent qui vient de modifier des fichiers.
"""
import subprocess
import sys

import pytest

from tools.coder.repo_engineer_tool import CODE_AUCUN_TEST, RepoEngineerTool


@pytest.fixture
def depot(tmp_path):
    """Un dépôt jouet, avec un seul test qui passe."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_jouet.py").write_text(
        "def test_vrai():\n    assert True\n", encoding="utf-8")
    return tmp_path


class TestValidation:
    def test_un_depot_sans_aucun_test_n_est_pas_un_succes(self, tmp_path):
        """« Aucun test collecté » est une absence de mesure, jamais un OK."""
        (tmp_path / "tests").mkdir()

        resultat = RepoEngineerTool(root_dir=str(tmp_path)).run_tests()

        assert resultat["success"] is False, (
            "un depot ou aucun test ne tourne a ete rapporte comme valide")
        assert resultat["tests_collectes"] == 0

    def test_des_tests_qui_passent_sont_un_succes(self, depot):
        resultat = RepoEngineerTool(root_dir=str(depot)).run_tests()

        assert resultat["success"] is True
        assert "1 passed" in resultat["stdout"]

    def test_un_test_qui_echoue_est_rapporte_comme_tel(self, depot):
        (depot / "tests" / "test_jouet.py").write_text(
            "def test_faux():\n    assert False\n", encoding="utf-8")

        resultat = RepoEngineerTool(root_dir=str(depot)).run_tests()

        assert resultat["success"] is False
        assert "1 failed" in resultat["stdout"]

    def test_une_suite_trop_longue_est_interrompue_et_le_dit(self, depot):
        """Un dépassement de délai n'est pas un échec de test : il se nomme."""
        (depot / "tests" / "test_jouet.py").write_text(
            "import time\n\ndef test_lent():\n    time.sleep(5)\n", encoding="utf-8")

        resultat = RepoEngineerTool(root_dir=str(depot)).run_tests(timeout=1)

        assert resultat["success"] is False
        assert "interrompus" in resultat["stderr"]
        assert resultat["tests_collectes"] is None, (
            "un delai depasse ne dit rien du nombre de tests")

    def test_le_code_de_sortie_sans_test_est_bien_celui_de_pytest(self, tmp_path):
        """Le 5 n'est pas une supposition sur pytest : il est mesuré ici."""
        (tmp_path / "vide").mkdir()

        res = subprocess.run([sys.executable, "-m", "pytest", "vide", "-q"],
                             cwd=str(tmp_path), capture_output=True, text=True)

        assert res.returncode == CODE_AUCUN_TEST


class TestEcriture:
    def test_un_chemin_hors_du_depot_n_est_jamais_ecrit(self, tmp_path):
        outil = RepoEngineerTool(root_dir=str(tmp_path / "depot"))
        (tmp_path / "depot").mkdir()
        dehors = tmp_path / "dehors.txt"

        resultat = outil.apply_patch({"../dehors.txt": "contenu"})

        assert resultat["success"] is False
        assert not dehors.exists(), "un fichier a ete ecrit hors du depot"

    def test_un_chemin_absolu_ne_sort_pas_non_plus(self, tmp_path):
        outil = RepoEngineerTool(root_dir=str(tmp_path / "depot"))
        (tmp_path / "depot").mkdir()
        cible = tmp_path / "absolu.txt"

        resultat = outil.apply_patch({str(cible): "contenu"})

        assert resultat["success"] is False
        assert not cible.exists()

    def test_un_fichier_du_depot_est_bien_ecrit(self, tmp_path):
        (tmp_path / "depot").mkdir()
        outil = RepoEngineerTool(root_dir=str(tmp_path / "depot"))

        resultat = outil.apply_patch({"src/module.py": "print('bonjour')\n"})

        assert resultat["success"] is True
        assert (tmp_path / "depot" / "src" / "module.py").read_text() == "print('bonjour')\n"
