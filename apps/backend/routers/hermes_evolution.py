"""`/api/hermes-evolution/evoluer` — déclenche une évolution GEPA sur un
dépôt CIBLE, jamais ARENA.

Pas d'aiguillage depuis le chat (comme `/api/video/projet`, DEC-0037) : ceci
est un outil de développement, pas une capacité métier UniC Plaquiste — le
propriétaire l'atteint par un appel direct. La proposition passe par
`registre.executer` comme tout le reste ; la confirmation réelle emprunte
la route générique déjà en place, `POST /api/actions/{identifiant}/confirm`
(`apps/backend/routers/actions.py`) — aucune route de confirmation dédiée
n'est nécessaire ici.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.backend.runtime import registre
from apps.backend.security import limiter_debit, verify_api_key

logger = logging.getLogger("usman.backend.hermes_evolution")

router = APIRouter()


class EvolutionRequest(BaseModel):
    #: Le dépôt hermes-agent CIBLE — jamais ARENA (refusé par le connecteur,
    #: pas seulement par cette route).
    depot_cible: str
    competence: str
    iterations: int = 3
    source_evaluation: str = "synthetic"
    timeout_secondes: Optional[float] = None


@router.post("/api/hermes-evolution/evoluer",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def proposer_evolution(request: EvolutionRequest) -> Dict[str, Any]:
    parametres: Dict[str, Any] = {
        "depot_cible": request.depot_cible,
        "competence": request.competence,
        "iterations": request.iterations,
        "source_evaluation": request.source_evaluation,
    }
    if request.timeout_secondes is not None:
        parametres["timeout_secondes"] = request.timeout_secondes

    resultat = registre.executer("hermes_evolution", "evoluer", **parametres)
    return resultat.to_dict()
