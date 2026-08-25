import logging
import re
from typing import Dict, Any, Optional
from core.models.base import ModelProvider
from tools.code.sandbox_interpreter import SandboxInterpreterTool

logger = logging.getLogger("arena.core.reasoning")

class ReasoningEngine:
    """Moteur de raisonnement structuré Plan & Solve sécurisé dans OpenSandbox."""

    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.interpreter = SandboxInterpreterTool()

    async def solve_complex_task(self, user_prompt: str) -> Dict[str, Any]:
        """Exécute un raisonnement profond en 3 étapes : Planification -> Calcul/Code -> Synthèse."""
        logger.info("Début du raisonnement profond (Plan & Solve en Bac à Sable)...")

        # 1. ÉTAPE DE PLANIFICATION
        plan_prompt = (
            "Tu es un moteur de raisonnement logique de haut niveau.\n"
            "Analyse la question suivante et décompose la résolution en 3 étapes claires.\n"
            "Si la question implique des maths, des statistiques ou des données, écris un script Python "
            "avec sympy/numpy/math pour calculer la réponse exacte.\n\n"
            f"Question: {user_prompt}\n\n"
            "Plan et Script Python (si nécessaire) dans des balises ```python ... ```:"
        )

        plan_res = await self.provider.generate(prompt=plan_prompt)

        # 2. ÉTAPE DE CALCUL / EXÉCUTION DANS OPENSANDBOX
        code_match = re.search(r"```python\n?(.*?)```", plan_res, re.DOTALL)
        execution_output = ""
        
        if code_match:
            python_code = code_match.group(1).strip()
            logger.info("Exécution du code de vérification dans le Bac à Sable OpenSandbox...")
            exec_res = self.interpreter.execute_python_code(python_code)
            
            if exec_res["success"]:
                execution_output = exec_res["stdout"]
            else:
                execution_output = f"Erreur calcul : {exec_res['stderr']}"

        # 3. ÉTAPE DE SYNTHÈSE SUBLIME
        synthesis_prompt = (
            "Tu es ARENA. Présente la solution finale de manière élégante, claire et irréprochable.\n"
            f"Question originale : {user_prompt}\n"
            f"Raisonnement & Plan : {plan_res}\n"
            f"Résultat des calculs exacts dans le Bac à Sable : {execution_output}\n\n"
            "Solution Finale Sublime :"
        )

        final_solution = await self.provider.generate(prompt=synthesis_prompt)

        return {
            "status": "success",
            "plan": plan_res.strip(),
            "calculation_result": execution_output,
            "final_response": final_solution.strip()
        }