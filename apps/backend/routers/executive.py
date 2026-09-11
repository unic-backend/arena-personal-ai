"""`/api/executive` — le point d'entree reel de l'Executive Intelligence
(mission ARENA x OPENEXECUTIVE, DEC-0086).

Meme discipline que `image_generation.py` : aucune orchestration ici, la
route delegue integralement a `ExecutiveAgent.run`, qui delegue lui-meme au
moteur (`core/executive/moteur.py`).
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.backend.runtime import executive_agent
from apps.backend.security import limiter_debit, verify_api_key
from core.executive.selection import ROLES

logger = logging.getLogger("usman.backend.executive")

router = APIRouter()


class AnalyserRequest(BaseModel):
    question: str


@router.post("/api/executive/analyser",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def analyser(request: AnalyserRequest) -> Dict[str, Any]:
    try:
        return await executive_agent.run(request.question)
    except Exception as erreur:  # noqa: BLE001 — une panne se rapporte, jamais un 500 muet
        logger.error("Analyse executive en echec : %s", erreur)
        raise HTTPException(status_code=500, detail=str(erreur)) from erreur


@router.get("/api/executive/roles",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def roles_disponibles() -> Dict[str, Any]:
    """Les roles que l'Executive Intelligence peut consulter, et les mots-cles
    qui les convoquent — jamais devine par un client qui appellerait sans
    savoir ce qui existe."""
    return {
        "roles": [
            {"id": r.identifiant, "domain": r.domaine, "keywords": list(r.mots_cles)}
            for r in ROLES
        ],
    }
