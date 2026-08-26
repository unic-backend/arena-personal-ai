import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.tools.repo_engineer")

class RepoEngineerTool:
    """Outil d'inspection, de modification multi-fichiers et de validation de dépôt (Inspiré d'Odysseus / Devin)."""

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()

    def get_tree(self, max_depth: int = 3) -> List[str]:
        """Affiche la structure arborescente du projet."""
        file_tree = []
        ignore_dirs = {".git", ".venv", "__pycache__", "node_modules", ".next", "dist"}

        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            rel_path = Path(root).relative_to(self.root_dir)
            depth = len(rel_path.parts)

            if depth <= max_depth:
                indent = "  " * depth
                file_tree.append(f"{indent}📁 {rel_path.name}/" if rel_path.name != "." else "📁 root/")
                for f in files:
                    if not f.endswith(('.pyc', '.gitkeep', '.db')):
                        file_tree.append(f"{indent}  📄 {f}")

        return file_tree

    def read_files(self, file_paths: List[str]) -> Dict[str, str]:
        """Lit simultanément le contenu de plusieurs fichiers du projet."""
        contents = {}
        for fp in file_paths:
            full_path = (self.root_dir / fp).resolve()
            try:
                full_path.relative_to(self.root_dir)
                if full_path.exists() and full_path.is_file():
                    contents[fp] = full_path.read_text(encoding="utf-8")
                else:
                    contents[fp] = f"❌ Fichier introuvable: {fp}"
            except Exception as e:
                contents[fp] = f"❌ Erreur de lecture: {e}"
        return contents

    def apply_patch(self, file_changes: Dict[str, str]) -> Dict[str, Any]:
        """Applique des modifications sur plusieurs fichiers simultanément."""
        applied = []
        errors = []

        for fp, new_content in file_changes.items():
            full_path = (self.root_dir / fp).resolve()
            try:
                full_path.relative_to(self.root_dir)
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(new_content, encoding="utf-8")
                applied.append(fp)
            except Exception as e:
                errors.append(f"{fp}: {str(e)}")

        return {
            "success": len(errors) == 0,
            "applied_files": applied,
            "errors": errors
        }

    def run_tests(self, test_path: Optional[str] = None) -> Dict[str, Any]:
        """Exécute la suite de tests unitaires pour valider les modifications."""
        target = test_path if test_path else "tests/"
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", target]

        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.root_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip()
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Erreur lancement tests: {e}"
            }

if __name__ == "__main__":
    tool = RepoEngineerTool()
    print("🛠️ RepoEngineerTool prêt. Fichiers projet détectés :", len(tool.get_tree(max_depth=1)))
