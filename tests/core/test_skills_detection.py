"""`core/skills/detection.py` — mission ARENA x AUTOSKILLS (DEC prochain,
10/09/2026).

Chaque test construit un petit projet réel dans `tmp_path` — jamais une
simulation de ce qu'un `package.json` "devrait" contenir.
"""
import json
from pathlib import Path

from core.skills.detection import detecter_combos, detecter_technologies


def _package_json(dossier: Path, deps=None, dev_deps=None):
    contenu = {}
    if deps:
        contenu["dependencies"] = {d: "*" for d in deps}
    if dev_deps:
        contenu["devDependencies"] = {d: "*" for d in dev_deps}
    (dossier / "package.json").write_text(json.dumps(contenu), encoding="utf-8")


class TestProjetVide:
    def test_dossier_vide_ne_detecte_rien(self, tmp_path):
        assert detecter_technologies(tmp_path) == []


class TestPython:
    def test_requirements_txt_detecte_python(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi==0.1\n", encoding="utf-8")
        technologies = detecter_technologies(tmp_path)
        assert "python" in technologies
        assert "fastapi" in technologies

    def test_pyproject_toml_detecte_python_sans_fastapi(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
        technologies = detecter_technologies(tmp_path)
        assert "python" in technologies
        assert "fastapi" not in technologies


class TestNode:
    def test_paquet_react_detecte(self, tmp_path):
        _package_json(tmp_path, deps=["react", "react-dom"])
        assert "react" in detecter_technologies(tmp_path)

    def test_paquet_devdependencies_aussi_lu(self, tmp_path):
        _package_json(tmp_path, dev_deps=["typescript", "vite"])
        technologies = detecter_technologies(tmp_path)
        assert "typescript" in technologies
        assert "vite" in technologies

    def test_fichier_config_detecte_sans_paquet(self, tmp_path):
        _package_json(tmp_path)
        (tmp_path / "tailwind.config.js").write_text("module.exports = {}", encoding="utf-8")
        assert "tailwindcss" in detecter_technologies(tmp_path)

    def test_package_json_absent_ne_plante_pas(self, tmp_path):
        assert detecter_technologies(tmp_path) == []

    def test_package_json_illisible_ne_plante_pas(self, tmp_path):
        (tmp_path / "package.json").write_text("{ceci n'est pas du json", encoding="utf-8")
        assert detecter_technologies(tmp_path) == []


class TestDocker:
    def test_dockerfile_seul_suffit(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")
        assert "docker" in detecter_technologies(tmp_path)


class TestGithubActions:
    def test_dossier_workflows_suffit(self, tmp_path):
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: CI\n", encoding="utf-8")
        assert "github-actions" in detecter_technologies(tmp_path)


class TestSousProjet:
    def test_apps_pwa_est_atteint(self, tmp_path):
        """Le cas réel de ce dépôt : la racine est Python, `apps/pwa/` a son
        propre `package.json`."""
        (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        pwa = tmp_path / "apps" / "pwa"
        pwa.mkdir(parents=True)
        _package_json(pwa, deps=["react"], dev_deps=["vite", "typescript"])

        technologies = detecter_technologies(tmp_path)
        assert set(technologies) == {"python", "fastapi", "react", "vite", "typescript"}

    def test_dockerfile_dans_un_sous_dossier_sans_manifeste_est_vu(self, tmp_path):
        """`apps/backend/Dockerfile` sans `package.json` ni `pyproject.toml`
        à lui — le vrai cas mesuré dans ARENA lui-même."""
        apps = tmp_path / "apps" / "backend"
        apps.mkdir(parents=True)
        (apps / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")

        assert "docker" in detecter_technologies(tmp_path)

    def test_node_modules_jamais_descendu(self, tmp_path):
        """Des milliers de `package.json` d'autrui ne doivent jamais être
        confondus avec le projet sondé."""
        nm = tmp_path / "node_modules" / "une-dependance"
        nm.mkdir(parents=True)
        _package_json(nm, deps=["some-totally-unrelated-package"])

        assert detecter_technologies(tmp_path) == []


class TestCombos:
    def test_combo_react_vite_typescript(self, tmp_path):
        _package_json(tmp_path, deps=["react"], dev_deps=["vite", "typescript"])
        technologies = detecter_technologies(tmp_path)
        assert detecter_combos(technologies) == ["react-vite-typescript"]

    def test_pas_de_combo_si_une_seule_technologie_manque(self, tmp_path):
        _package_json(tmp_path, deps=["react"], dev_deps=["vite"])
        technologies = detecter_technologies(tmp_path)
        assert detecter_combos(technologies) == []


class TestReel:
    def test_le_vrai_depot_arena(self):
        """Vérité terrain, sur ARENA lui-même — pas une simulation."""
        racine = Path(__file__).resolve().parents[2]
        technologies = detecter_technologies(racine)
        attendues = {"python", "fastapi", "react", "typescript", "vite",
                     "tailwindcss", "vitest", "docker", "github-actions"}
        assert attendues.issubset(set(technologies))
