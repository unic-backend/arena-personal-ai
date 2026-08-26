import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

from tools.code.code_interpreter_tool import CodeInterpreterTool

logger = logging.getLogger("arena.tools.sandbox_interpreter")

# Le repli hors bac a sable execute le code directement sur la machine, sans
# isolation ni limite memoire. Il n'est permis que derriere ce flag explicite.
FLAG_EXECUTION_NON_ISOLEE = "ALLOW_UNSAFE_EXEC"
VALEURS_VRAIES = {"1", "true", "yes", "oui"}

class SandboxInterpreterTool:
    """Interpréteur de code exécuté dans un bac à sable Docker étanche.

    Sans bac à sable, l'exécution est **refusée**, jamais dégradée : un repli
    silencieux sur l'hôte annulerait la seule protection de l'outil. Le repli
    reste possible, mais seulement si ALLOW_UNSAFE_EXEC est explicitement activé.
    """

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

    @staticmethod
    def _repli_non_isole_autorise() -> bool:
        """Vrai uniquement si le propriétaire a activé ALLOW_UNSAFE_EXEC."""
        valeur = os.getenv(FLAG_EXECUTION_NON_ISOLEE, "").strip().lower()
        return valeur in VALEURS_VRAIES

    @staticmethod
    def _refuser(clean_code: str, raison: str) -> Dict[str, Any]:
        """Réponse renvoyée quand aucun bac à sable n'est disponible.

        Le refus est définitif : `refused` signale à l'appelant qu'il est inutile
        de demander une correction du code, ce n'est pas le code qui a échoué.
        """
        message = (
            f"Exécution refusée par sécurité : {raison} "
            f"Démarre Docker, ou active {FLAG_EXECUTION_NON_ISOLEE}=true "
            f"pour exécuter le code directement sur la machine, sans isolation."
        )
        logger.error(message)
        return {
            "success": False,
            "refused": True,
            "exit_code": -1,
            "stdout": "",
            "stderr": message,
            "error": message,
            "executed_code": clean_code,
            "sandbox_mode": "REFUSED",
        }

    def execute_python_code(self, code_str: str) -> Dict[str, Any]:
        """Exécute le code dans un conteneur Docker isolé ou bascule sur l'interpréteur local avec avertissement explicite."""
        clean_code = code_str.replace("```python", "").replace("```", "").strip()

        # Docker inactif : aucun bac à sable, donc aucune exécution.
        if not self.docker_available:
            if not self._repli_non_isole_autorise():
                return self._refuser(clean_code, "le démon Docker est inactif.")
            logger.warning(
                "⚠️ %s actif : exécution sur la machine hôte, SANS isolation ni limite mémoire.",
                FLAG_EXECUTION_NON_ISOLEE,
            )
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
            if not self._repli_non_isole_autorise():
                return self._refuser(clean_code, f"le bac à sable Docker a échoué ({e}).")
            logger.warning(
                "⚠️ Échec du bac à sable Docker (%s) et %s actif : exécution sur la machine hôte.",
                e, FLAG_EXECUTION_NON_ISOLEE,
            )
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
    if sandbox.docker_available:
        etat = "ACTIF & ÉTANCHÉ"
    elif SandboxInterpreterTool._repli_non_isole_autorise():
        etat = f"⚠️ INACTIF ({FLAG_EXECUTION_NON_ISOLEE} actif : exécution sur l'hôte)"
    else:
        etat = "INACTIF (exécution refusée)"
    print("🛡️ Statut Docker Sandbox:", etat)
    r = sandbox.execute_python_code("print('Hello depuis OpenSandbox ARENA !')")
    print("Mode:", r["sandbox_mode"])
    print("Sortie:", r["stdout"] or r["stderr"])
