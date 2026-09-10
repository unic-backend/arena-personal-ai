"""`/api/image` — le point d'entree reel de la capacite image-generation
canonique (mission ARENA x HIDREAM-I1, DEC-0085).

Meme discipline que `video_production.py`/`personnages.py` : aucune logique
d'orchestration ici, seulement la route. La generation passe par
`VideoProductionAgent.generer_image` (donc par le connecteur `hidream`, donc
par la file de confirmation) ; l'etat et les capacites relisent directement
le registre, comme `connectors.py` le fait deja pour les autres moteurs.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.backend.runtime import registre, video_production_agent
from apps.backend.security import limiter_debit, verify_api_key

logger = logging.getLogger("usman.backend.image_generation")

router = APIRouter()


class GenererImageRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    seed: Optional[int] = None
    #: "full" | "dev" | "fast" — laisse au connecteur/worker le defaut
    #: (la variante la plus legere) si absent.
    variante: Optional[str] = None


@router.post("/api/image/generer",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def generer_image(request: GenererImageRequest) -> Dict[str, Any]:
    try:
        return await video_production_agent.generer_image(
            request.prompt, negative_prompt=request.negative_prompt,
            width=request.width, height=request.height, seed=request.seed,
            variante=request.variante)
    except Exception as erreur:  # noqa: BLE001 — une panne se rapporte, jamais un 500 muet
        logger.error("Generation image en echec : %s", erreur)
        raise HTTPException(status_code=500, detail=str(erreur)) from erreur


@router.get("/api/image/capacites",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def capacites_image() -> Dict[str, Any]:
    """Ce que le worker HiDream sait faire, et le materiel qu'il a mesure —
    jamais suppose disponible depuis ce seul appel."""
    resultat = registre.executer("hidream", "capacites")
    return resultat.to_dict()


@router.get("/api/image/{job_id}",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def etat_image(job_id: str) -> Dict[str, Any]:
    resultat = registre.executer("hidream", "etat_travail", job_id=job_id)
    return resultat.to_dict()
