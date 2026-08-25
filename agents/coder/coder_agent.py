import logging
from typing import Dict, Any, Optional

from core.agent.base_agent import BaseAgent
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager
from tools.code.code_interpreter_tool import CodeInterpreterTool

logger = logging.getLogger("arena.agent.coder")

class CoderAgent(BaseAgent):
    """Agent autonome de programmation avec auto-correction via CodeInterpreter."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="CoderAgent",
            description="Agent autonome spécialisé en programmation et résolution de bugs.",
            provider=provider,
            memory=memory
        )
        self.interpreter = CodeInterpreterTool()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info("CoderAgent au travail...")
        
        prompt = (
            "Tu es CoderAgent, un expert absolu en Python et programmation.\n"
            "Écris un script Python valide et autonome pour résoudre ce problème.\n"
            "Ne mets AUCUN texte explicatif, réponds UNIQUEMENT avec le bloc de code Python dans des balises ```python ... ```.\n\n"
            f"Problème: {user_input}"
        )

        raw_code = await self.provider.generate(prompt=prompt)
        res = self.interpreter.execute_python_code(raw_code)
        
        attempts = 0
        while not res["success"] and attempts < 2:
            attempts += 1
            logger.warning(f"Bug détecté dans le code (Essai {attempts}). Auto-correction en cours...")
            
            executed_code = res.get("executed_code", "")
            stderr_msg = res.get("stderr", "")
            
            fix_prompt = (
                "Le code Python suivant a produit une erreur lors de l'exécution:\n\n"
                "[CODE PROPOSÉ]\n"
                "```python\n"
                + executed_code + "\n"
                "```\n\n"
                "[ERREUR PRODUITE]\n"
                "```\n"
                + stderr_msg + "\n"
                "```\n\n"
                "Corrige le code pour qu'il s'exécute parfaitement sans aucune erreur.\n"
                "Réponds UNIQUEMENT avec le code corrigé dans des balises ```python ... ```."
            )

            raw_code = await self.provider.generate(prompt=fix_prompt)
            res = self.interpreter.execute_python_code(raw_code)

        code_out = res.get("executed_code", "")
        stdout_out = res.get("stdout", "")
        stderr_out = res.get("stderr", "")

        if res["success"]:
            response_msg = (
                f"Code exécuté et vérifié avec succès ({attempts + 1} essai(s)) !\n\n"
                f"```python\n{code_out}\n```\n\n"
                f"**Résultat de l'exécution :**\n```\n{stdout_out}\n```"
            )
            return {
                "status": "success",
                "agent": self.name,
                "auto_corrected": (attempts > 0),
                "attempts": attempts + 1,
                "code": code_out,
                "stdout": stdout_out,
                "response": response_msg
            }
        else:
            response_msg = (
                f"Échec de l'auto-correction après {attempts + 1} essais.\n\n"
                f"**Code :**\n```python\n{code_out}\n```\n\n"
                f"**Erreur :**\n```\n{stderr_out}\n```"
            )
            return {
                "status": "error",
                "agent": self.name,
                "attempts": attempts + 1,
                "code": code_out,
                "stderr": stderr_out,
                "response": response_msg
            }