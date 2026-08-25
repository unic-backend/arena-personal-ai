import os
import sys
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any

from tools.code.code_interpreter_tool import CodeInterpreterTool

logger = logging.getLogger("arena.tools.sandbox_interpreter")

class SandboxInterpreterTool:
    """Interpréteur de code sécurisé dans un bac à sable Docker étanche ou Fallback Local explicitement averti."""

    def __init__(self, timeout_seconds: int = 20, memory_limit: str = "512m"):
        self.timeout_seconds = timeout_seconds
        self.memory_limit = memory_limit
        self.fallback_tool = CodeInterpreterTool(timeout_seconds=timeout_seconds)
        self.docker_available = self._check_docker()

    def _check_docker(self) -> bool:
        """Vérifie si le démon Docker est actif sur la machine."""
        try:
            res = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3
            )
            return res.returncode == 0
        except Exception:
            return False

    def execute_python_code(self, code_str: str) -> Dict[str, Any]:
        """Exécute le code dans un conteneur Docker isolé ou bascule sur l'interpréteur local avec avertissement explicite."""
        clean_code = code_str.replace("```python", "").replace("```", "").strip()

        # Si Docker n'est pas actif -> Avertissement explicite et fallback
        if not self.docker_available:
            logger.warning("⚠️ DOCKER INACTIF: Exécution du code en mode FALLBACK LOCAL (Bac à sable Docker non engagé).")
            res = self.fallback_tool.execute_python_code(clean_code)
            res["sandbox_mode"] = "⚠️ LOCAL FALLBACK (Docker inactif)"
            return res

        # Exécution dans le Bac à sable Docker
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp_file:
            tmp_file.write(clean_code)
            tmp_file_path = Path(tmp_file.name).resolve()

        try:
            logger.info("🛡️ Exécution sécurisée dans le Bac à Sable Docker isolée (OpenSandbox Pattern)...")
            
            cmd = [
                "docker", "run", "--rm",
                "--network", "none",
                "--memory", self.memory_limit,
                "-v", f"{tmp_file_path}:/app/script.py:ro",
                "arena-sandbox",
                "python", "/app/script.py"
            ]

            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_seconds
            )

            success = (res.returncode == 0)
            return {
                "success": success,
                "exit_code": res.returncode,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
                "executed_code": clean_code,
                "sandbox_mode": "🛡️ Docker Isolated Sandbox"
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"❌ Erreur Bac à Sable: Temps d'exécution dépassé ({self.timeout_seconds}s).",
                "executed_code": clean_code,
                "sandbox_mode": "🛡️ Docker Isolated Sandbox"
            }
        except Exception as e:
            logger.error(f"Échec Docker Sandbox, bascule fallback : {e}")
            res = self.fallback_tool.execute_python_code(clean_code)
            res["sandbox_mode"] = "⚠️ LOCAL FALLBACK (Erreur Docker)"
            return res
        finally:
            if tmp_file_path.exists():
                try:
                    tmp_file_path.unlink()
                except Exception:
                    pass

if __name__ == "__main__":
    sandbox = SandboxInterpreterTool()
    print("🛡️ Statut Docker Sandbox:", "ACTIF & ÉTANCHÉ" if sandbox.docker_available else "⚠️ INACTIF (Mode Fallback Local)")
    r = sandbox.execute_python_code("print('Hello depuis OpenSandbox ARENA !')")
    print("Sortie:", r["stdout"])