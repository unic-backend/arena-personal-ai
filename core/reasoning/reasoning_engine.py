"""Raisonner en plusieurs etapes, sans perdre le fil quand une etape tombe.

Ce moteur enchainait trois etapes en ligne droite : plan, calcul, synthese. Si
le calcul echouait, personne ne savait dire ou la chaine s'etait arretee, ni
combien de fois on avait essaye, ni ce qui restait exploitable.

Il tourne maintenant sur `core/execution/coordination.py`, qui garde l'etat :
quelle etape, combien de tentatives, ce qui a ete abandonne et pourquoi.

**Ce que ca change, concretement :**

1. **Le calcul est facultatif.** Un bac a sable absent n'emporte plus la
   reponse : l'etape est marquee `ABANDONNEE`, sa raison est gardee, et la
   synthese se fait avec ce qu'on a — en le disant.

2. **La synthese est verifiee.** Une reponse vide n'est pas une reponse : le
   controle est declare, et l'etape est retentee avant d'etre declaree ratee.

3. **Rien n'est retente sans fin.** Deux tentatives pour ce qui depend d'un
   service, **une seule** pour le calcul : rejouer un code deterministe rend la
   meme erreur, et fait perdre le temps de deux executions.

4. **L'etat sort avec la reponse.** `coordination` porte les etapes reelles,
   pour que l'interface montre ce qui s'est passe au lieu de le deviner.
"""
import logging
import re
from typing import Any, Dict, Tuple

from core.execution.coordination import Coordination, Etape, EtatEtape
from core.models.base import ModelProvider
from tools.code.sandbox_interpreter import SandboxInterpreterTool

logger = logging.getLogger("usman.core.reasoning")

#: Un service peut tomber une fois. Deux tentatives, pas plus.
ESSAIS_MODELE = 2

#: Le calcul, lui, n'est PAS retente : le meme code rend la meme erreur, et on
#: aurait paye deux executions pour la meme reponse.
ESSAIS_CALCUL = 1

BLOC_PYTHON = re.compile(r"```python\n?(.*?)```", re.DOTALL)


def _non_vide(sortie: Any) -> Tuple[bool, str]:
    """Une reponse vide n'est pas une reponse."""
    return (bool(str(sortie or "").strip()), "le modele n'a rien rendu")


def _calcul_reussi(sortie: Any) -> Tuple[bool, str]:
    """Le bac a sable dit lui-meme s'il a execute. On ne le suppose pas."""
    if not isinstance(sortie, dict):
        return False, "le bac a sable n'a rien rendu d'exploitable"
    if sortie.get("success"):
        return True, ""
    return False, str(sortie.get("stderr") or "execution refusee")[:200]


class ReasoningEngine:
    """Raisonnement profond : plan, calcul reellement execute, puis synthese."""

    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.interpreter = SandboxInterpreterTool()

    async def solve_complex_task(self, user_prompt: str) -> Dict[str, Any]:
        """Conduit les trois etapes et rend l'etat complet de la tache."""
        logger.info("Raisonnement profond : plan, calcul, synthese.")

        plan_prompt = (
            "Tu es un moteur de raisonnement logique de haut niveau.\n"
            "Analyse la question suivante et décompose la résolution en 3 étapes claires.\n"
            "Si la question implique des maths, des statistiques ou des données, écris un script Python "
            "avec sympy/numpy/math pour calculer la réponse exacte.\n\n"
            f"Question: {user_prompt}\n\n"
            "Plan et Script Python (si nécessaire) dans des balises ```python ... ```:"
        )

        async def planifier() -> str:
            return await self.provider.generate(prompt=plan_prompt)

        def calculer(acquis: Dict[str, Any]) -> Dict[str, Any]:
            """N'est lancee que si le plan porte du code. Sinon, rien a executer."""
            trouve = BLOC_PYTHON.search(acquis.get("plan") or "")
            if not trouve:
                # Pas de code : ce n'est pas un echec, il n'y a rien a faire.
                return {"success": True, "stdout": "", "sans_code": True}
            logger.info("Execution du code de verification dans le bac a sable.")
            return self.interpreter.execute_python_code(trouve.group(1).strip())

        async def synthetiser(acquis: Dict[str, Any]) -> str:
            calcul = acquis.get("calcul") or {}
            sortie = calcul.get("stdout", "") if calcul.get("success") else ""
            return await self.provider.generate(prompt=(
                "Tu es Usman. Présente la solution finale de manière élégante, "
                "claire et irréprochable.\n"
                f"Question originale : {user_prompt}\n"
                f"Raisonnement & Plan : {acquis.get('plan', '')}\n"
                f"Résultat des calculs exacts dans le Bac à Sable : {sortie}\n\n"
                "Solution Finale Sublime :"))

        coordination = Coordination(f"raisonnement : {user_prompt[:40]}", [
            Etape("plan", planifier, essais_max=ESSAIS_MODELE, verifier=_non_vide),
            # Facultative : un bac a sable absent ne doit pas emporter la reponse.
            Etape("calcul", calculer, essais_max=ESSAIS_CALCUL, facultative=True,
                  verifier=_calcul_reussi, depend_de=("plan",)),
            Etape("synthese", synthetiser, essais_max=ESSAIS_MODELE,
                  verifier=_non_vide, depend_de=("plan",)),
        ])
        etat = await coordination.executer()

        trace_calcul = etat.trace_de("calcul")
        calcul = trace_calcul.resultat if trace_calcul else None
        if trace_calcul is not None and trace_calcul.etat is EtatEtape.ABANDONNEE:
            # Le format historique est conserve : le routeur de chat lit cette
            # chaine pour avertir que rien n'a ete calcule.
            resultat_calcul = f"Erreur calcul : {trace_calcul.raison}"
        elif isinstance(calcul, dict) and not calcul.get("sans_code"):
            resultat_calcul = calcul.get("stdout", "")
        else:
            resultat_calcul = ""

        return {
            "status": "success" if etat.aboutie else "error",
            "plan": str(etat.resultats.get("plan", "")).strip(),
            "calculation_result": resultat_calcul,
            "final_response": str(etat.resultats.get("synthese", "")).strip(),
            # L'etat reel des etapes, pour que l'interface montre ce qui s'est
            # passe au lieu de l'inventer.
            "coordination": etat.to_dict(),
        }
