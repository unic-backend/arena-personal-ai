"""Bac à sable : ce qu'il fait quand il est là, et ce qu'il refuse quand il ne l'est pas.

Les tests d'isolation exigent un démon Docker actif : ils portent le marqueur
`integration` et sont désélectionnés par défaut. Le refus, lui, se vérifie partout.
"""
import pytest

from tools.code.sandbox_interpreter import SandboxInterpreterTool

CODE_TEMOIN = "print('ce code ne devrait pas s executer')"


@pytest.fixture
def sans_docker(monkeypatch) -> SandboxInterpreterTool:
    """Bac à sable dont le démon Docker est indisponible, flag de repli retiré."""
    monkeypatch.delenv("ALLOW_UNSAFE_EXEC", raising=False)
    bac = SandboxInterpreterTool()
    monkeypatch.setattr(bac, "docker_available", False)
    return bac


def test_sans_bac_a_sable_l_execution_est_refusee(sans_docker):
    res = sans_docker.execute_python_code(CODE_TEMOIN)

    assert res["success"] is False
    assert res["refused"] is True
    assert res["sandbox_mode"] == "REFUSED"
    assert res["stdout"] == ""


def test_le_refus_ecrit_reellement_rien_sur_le_disque(sans_docker, tmp_path):
    temoin = tmp_path / "preuve.txt"
    res = sans_docker.execute_python_code(f"open({str(temoin)!r}, 'w').write('execute')")

    assert res["sandbox_mode"] == "REFUSED"
    assert not temoin.exists()


@pytest.mark.parametrize("valeur", ["", "false", "0", "non", "peut-etre"])
def test_une_valeur_non_reconnue_n_autorise_pas_le_repli(sans_docker, monkeypatch, valeur):
    """Une autorisation ne se devine pas : tout ce qui n'est pas un oui explicite est un non."""
    monkeypatch.setenv("ALLOW_UNSAFE_EXEC", valeur)

    assert sans_docker.execute_python_code(CODE_TEMOIN)["sandbox_mode"] == "REFUSED"


@pytest.mark.parametrize("valeur", ["1", "true", "TRUE", "yes", "oui"])
def test_le_flag_explicite_reautorise_le_repli(sans_docker, monkeypatch, valeur):
    monkeypatch.setenv("ALLOW_UNSAFE_EXEC", valeur)

    res = sans_docker.execute_python_code("print('repli assume')")

    assert res["success"] is True
    assert res["stdout"] == "repli assume"
    assert "FALLBACK" in res["sandbox_mode"]


def test_un_echec_du_conteneur_ne_bascule_pas_sur_l_hote(monkeypatch, tmp_path):
    """Docker annoncé actif mais injoignable : refus, pas exécution sur la machine."""
    monkeypatch.delenv("ALLOW_UNSAFE_EXEC", raising=False)
    bac = SandboxInterpreterTool()
    monkeypatch.setattr(bac, "docker_available", True)
    monkeypatch.setenv("PATH", str(tmp_path))  # plus aucun binaire `docker` atteignable

    res = bac.execute_python_code(CODE_TEMOIN)

    assert res["sandbox_mode"] == "REFUSED"
    assert res["stdout"] == ""


# --- Isolation réelle : exige un démon Docker et l'image usman-sandbox ---

@pytest.fixture
def bac_docker() -> SandboxInterpreterTool:
    bac = SandboxInterpreterTool()
    if not bac.docker_available:
        pytest.skip("Démon Docker inactif : l'isolation ne peut pas être mesurée ici.")
    return bac


@pytest.mark.integration
def test_docker_execute_un_calcul(bac_docker):
    res = bac_docker.execute_python_code("import math; print(round(math.pi, 4))")

    assert res["success"] is True
    assert "3.1416" in res["stdout"]


@pytest.mark.integration
def test_docker_fournit_les_outils_de_calcul(bac_docker):
    res = bac_docker.execute_python_code(
        "import sympy; x = sympy.Symbol('x'); print(sympy.solve(x**2 - 5*x + 6, x))"
    )

    assert res["success"] is True
    assert "[2, 3]" in res["stdout"]


@pytest.mark.integration
def test_docker_bloque_l_acces_au_disque_de_la_machine(bac_docker):
    res = bac_docker.execute_python_code("import os; print(os.listdir('/'))")

    assert res["success"] is False


@pytest.mark.integration
def test_docker_bloque_l_acces_a_internet(bac_docker):
    res = bac_docker.execute_python_code(
        "import urllib.request; print(urllib.request.urlopen('http://example.com', timeout=5).status)"
    )

    assert res["success"] is False


class TestImageAbsente:
    """Une image non construite est un problème d'installation, pas de code.

    Sans ce garde, `docker run` rendait un code de sortie non nul **sans
    lever** : « Unable to find image » remontait à l'appelant comme une
    erreur de code, et un agent essayait de corriger du code correct.
    Mesuré par lecture le 01/09/2026 ; Docker n'existe pas sur cette
    machine, donc le chemin est reproduit ici avec des doubles.
    """

    @pytest.fixture
    def docker_sans_image(self, monkeypatch):
        monkeypatch.setattr(SandboxInterpreterTool, "_check_docker", lambda self: True)
        monkeypatch.setattr(SandboxInterpreterTool, "_check_image", lambda self: False)
        monkeypatch.delenv("ALLOW_UNSAFE_EXEC", raising=False)

    def test_l_execution_est_refusee_et_nomme_l_image(self, docker_sans_image):
        resultat = SandboxInterpreterTool().execute_python_code("print(1)")
        assert resultat["refused"] is True
        assert "usman-sandbox" in resultat["stderr"]
        assert "docker build" in resultat["stderr"], (
            "le refus doit dire comment le réparer"
        )

    def test_le_refus_ne_se_confond_pas_avec_un_echec_de_code(self, docker_sans_image):
        resultat = SandboxInterpreterTool().execute_python_code("print(1)")
        assert resultat["sandbox_mode"] == "REFUSED"
        assert resultat["success"] is False

    def test_le_repli_reste_derriere_le_meme_interrupteur(self, monkeypatch):
        """Image absente ne doit pas ouvrir une porte que Docker absent ferme."""
        monkeypatch.setattr(SandboxInterpreterTool, "_check_docker", lambda self: True)
        monkeypatch.setattr(SandboxInterpreterTool, "_check_image", lambda self: False)
        monkeypatch.setenv("ALLOW_UNSAFE_EXEC", "true")

        outil = SandboxInterpreterTool()
        outil.fallback_tool.execute_python_code = lambda code: {
            "success": True, "stdout": "2", "stderr": "", "executed_code": code}
        resultat = outil.execute_python_code("print(1+1)")
        assert resultat["sandbox_mode"] == "⚠️ LOCAL FALLBACK (image absente)"

    def test_l_image_n_est_pas_sondee_quand_docker_dort(self, monkeypatch):
        """`docker image inspect` sans démon coûte une seconde pour rien."""
        appels = []
        monkeypatch.setattr(SandboxInterpreterTool, "_check_docker", lambda self: False)
        monkeypatch.setattr(SandboxInterpreterTool, "_check_image",
                            lambda self: appels.append("sondee") or False)
        SandboxInterpreterTool()
        assert appels == []
