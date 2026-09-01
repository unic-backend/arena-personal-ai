import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from tools.code.code_interpreter_tool import CodeInterpreterTool
from tools.docker_local import demon_repond, image_construite

logger = logging.getLogger("usman.tools.sandbox_interpreter")

# Le repli hors bac a sable execute le code directement sur la machine, sans
# isolation ni limite memoire. Il n'est permis que derriere ce flag explicite.
FLAG_EXECUTION_NON_ISOLEE = "ALLOW_UNSAFE_EXEC"

#: L'image du bac a sable. Nommee ici parce que deux endroits la verifient :
#: la sonde de demarrage et la commande d'execution.
IMAGE_BAC_A_SABLE = "usman-sandbox"
VALEURS_VRAIES = {"1", "true", "yes", "oui"}

#: Duree pendant laquelle une mesure NEGATIVE est reutilisee sans re-sonder.
#: Assez courte pour qu'un Docker demarre apres ARENA soit vu tout seul,
#: assez longue pour ne pas payer `docker info` a chaque bloc de code.
DUREE_DE_LA_MESURE = 30.0

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
        # Mesuree seulement si Docker repond : `docker image inspect`
        # sans demon coute une seconde pour rien.
        self.image_disponible = (
            self._check_image() if self.docker_available else False)
        self._mesure_le = time.monotonic()

    def _check_docker(self) -> bool:
        """Vérifie si le démon Docker est actif sur la machine.

        La sonde vit dans `tools/docker_local.py` : le moteur de graphe pose
        exactement la même question, et ne la posait pas du tout.
        """
        return demon_repond()

    def _check_image(self) -> bool:
        """L'image du bac a sable est-elle construite ?

        Sans elle, `docker run` rend un code de sortie NON NUL sans lever :
        le chemin d'exception n'est jamais pris, et « Unable to find image »
        remontait a l'appelant comme une erreur DE CODE. Un agent essayait
        alors de corriger du code correct. Un probleme d'installation se
        rapporte comme tel — c'est exactement ce que `_refuser` existe pour
        dire (« ce n'est pas le code qui a echoue »).
        """
        return image_construite(IMAGE_BAC_A_SABLE)

    def _rafraichir_la_mesure(self) -> None:
        """Re-sonde Docker quand la derniere mesure disait « non ».

        La mesure etait prise une seule fois, dans `__init__`. Or `CoderAgent`
        et `ReasoningEngine` sont construits au demarrage du serveur
        (`apps/backend/runtime.py`) : un Docker lance APRES ARENA n'etait jamais
        revu, et le refus repetait « demarre Docker » a quelqu'un qui venait de
        le demarrer. Seul un redemarrage du serveur le debloquait.

        L'asymetrie est voulue. Une mesure NEGATIVE se re-sonde : l'absence
        peut cesser sans que personne ne previenne. Une mesure POSITIVE ne se
        re-sonde pas : si le demon a disparu entre-temps, `docker run` echoue
        et le chemin d'exception refuse deja — l'execution est sa propre sonde.
        C'est la convention des connecteurs (`core/connectors/base.py` mesure
        avant chaque capacite), au cout d'appel pres.
        """
        if self.docker_available and self.image_disponible:
            return
        if time.monotonic() - self._mesure_le < DUREE_DE_LA_MESURE:
            return
        self.docker_available = self._check_docker()
        self.image_disponible = (
            self._check_image() if self.docker_available else False)
        self._mesure_le = time.monotonic()

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
        self._rafraichir_la_mesure()

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

        # Image absente : c'est un probleme d'installation, pas de code.
        if not self.image_disponible:
            if not self._repli_non_isole_autorise():
                return self._refuser(
                    clean_code,
                    f"l'image « {IMAGE_BAC_A_SABLE} » n'est pas construite "
                    f"(`docker build -t {IMAGE_BAC_A_SABLE} .`).")
            logger.warning(
                "⚠️ Image %s absente et %s actif : exécution sur la machine hôte.",
                IMAGE_BAC_A_SABLE, FLAG_EXECUTION_NON_ISOLEE)
            res = self.fallback_tool.execute_python_code(clean_code)
            res["sandbox_mode"] = "⚠️ LOCAL FALLBACK (image absente)"
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
                IMAGE_BAC_A_SABLE,
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
                except OSError as erreur:
                    # Un temporaire qui ne part pas n'est pas une raison de
                    # casser l'execution — mais un `pass` muet le rendait
                    # invisible, et le dossier se remplissait sans temoin.
                    logger.warning("Temporaire non supprime (%s) : %s",
                                   tmp_file_path, erreur)

if __name__ == "__main__":
    sandbox = SandboxInterpreterTool()
    if sandbox.docker_available:
        etat = "ACTIF & ÉTANCHÉ"
    elif SandboxInterpreterTool._repli_non_isole_autorise():
        etat = f"⚠️ INACTIF ({FLAG_EXECUTION_NON_ISOLEE} actif : exécution sur l'hôte)"
    else:
        etat = "INACTIF (exécution refusée)"
    print("🛡️ Statut Docker Sandbox:", etat)
    r = sandbox.execute_python_code("print('Hello depuis OpenSandbox Usman !')")
    print("Mode:", r["sandbox_mode"])
    print("Sortie:", r["stdout"] or r["stderr"])
