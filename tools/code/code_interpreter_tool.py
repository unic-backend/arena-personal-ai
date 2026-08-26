import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("arena.tools.code_interpreter")

class CodeInterpreterTool:
    """Outil d'exécution de code Python local sécurisé avec capture d'erreurs."""

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    def execute_python_code(self, code_str: str) -> Dict[str, Any]:
        """Exécute un bloc de code Python dans un processus isolé et renvoie le résultat."""

        # Nettoyage des balises markdown si présentes
        clean_code = code_str.replace("```python", "").replace("```", "").strip()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp_file:
            tmp_file.write(clean_code)
            tmp_path = tmp_file.name

        try:
            logger.info("Exécution du code Python par l'Interpreter...")
            res = subprocess.run(
                [sys.executable, tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_seconds
            )

            output = res.stdout.strip()
            error = res.stderr.strip()
            success = (res.returncode == 0)

            return {
                "success": success,
                "exit_code": res.returncode,
                "stdout": output,
                "stderr": error,
                "executed_code": clean_code
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"❌ Erreur: Temps d'exécution dépassé ({self.timeout_seconds}s).",
                "executed_code": clean_code
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"❌ Erreur système: {str(e)}",
                "executed_code": clean_code
            }
        finally:
            if Path(tmp_path).exists():
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass

if __name__ == "__main__":
    tool = CodeInterpreterTool()
    res = tool.execute_python_code("import sys; print(f'Hello de Python {sys.version.split()[0]} via Code Interpreter !')")
    print(f"Statut: {res['success']}")
    print(f"Sortie: {res['stdout']}")
