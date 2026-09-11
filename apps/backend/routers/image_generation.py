"""`/api/image` — le point d'entree reel de la capacite image-generation
canonique (mission ARENA x HIDREAM-I1 puis x COMFYUI, DEC-0085 et DEC-0087).

Meme discipline que `video_production.py`/`personnages.py` : aucune logique
d'orchestration ici, seulement la route. La generation passe par
`VideoProductionAgent.generer_image` (donc par la file de confirmation) ;
l'etat et les capacites relisent directement le registre, comme
`connectors.py` le fait deja pour les autres moteurs.

`backend` choisit le moteur (« hidream » ou « comfyui ») ; par defaut
`hidream`, pour ne rien changer au comportement mesure par DEC-0085.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.backend.runtime import registre, video_production_agent
from apps.backend.security import limiter_debit, verify_api_key
from core.production import comfyui_workflows
from core.production.image_backend_router import BACKEND_PAR_DEFAUT

logger = logging.getLogger("usman.backend.image_generation")

router = APIRouter()


class GenererImageRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    seed: Optional[int] = None
    #: "full" | "dev" | "fast" (HiDream uniquement) — laisse au connecteur
    #: le defaut si absent.
    variante: Optional[str] = None
    #: "hidream" | "comfyui" — absent : comportement DEC-0085 inchange.
    backend: Optional[str] = None
    #: ComfyUI uniquement : l'identifiant du workflow approuve
    #: (`GET /api/image/workflows`).
    workflow_id: Optional[str] = None
    ckpt_name: Optional[str] = None
    steps: Optional[int] = None
    cfg: Optional[float] = None


@router.post("/api/image/generer",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def generer_image(request: GenererImageRequest) -> Dict[str, Any]:
    try:
        return await video_production_agent.generer_image(
            request.prompt, negative_prompt=request.negative_prompt,
            width=request.width, height=request.height, seed=request.seed,
            variante=request.variante, backend=request.backend,
            workflow_id=request.workflow_id, ckpt_name=request.ckpt_name,
            steps=request.steps, cfg=request.cfg)
    except Exception as erreur:  # noqa: BLE001 — une panne se rapporte, jamais un 500 muet
        logger.error("Generation image en echec : %s", erreur)
        raise HTTPException(status_code=500, detail=str(erreur)) from erreur


@router.get("/api/image/capacites",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def capacites_image(backend: str = BACKEND_PAR_DEFAUT) -> Dict[str, Any]:
    """Ce que le moteur choisi sait faire, et le materiel qu'il a mesure —
    jamais suppose disponible depuis ce seul appel. `backend` par defaut :
    `hidream`, comportement DEC-0085 inchange."""
    resultat = registre.executer(backend, "capacites")
    return resultat.to_dict()


@router.get("/api/image/workflows",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def workflows_comfyui() -> Dict[str, Any]:
    """Le catalogue CONTROLE des workflows ComfyUI approuves (mission ARENA
    x COMFYUI, DEC-0087) — une lecture pure, deterministe, qui ne suppose
    JAMAIS qu'un serveur ComfyUI repond (`core/production/
    comfyui_workflows.py`, jamais atteint via le connecteur ici)."""
    return {"workflows": comfyui_workflows.lister()}


@router.get("/api/image/{job_id}",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def etat_image(job_id: str, backend: str = BACKEND_PAR_DEFAUT) -> Dict[str, Any]:
    resultat = registre.executer(backend, "etat_travail", job_id=job_id)
    return resultat.to_dict()
