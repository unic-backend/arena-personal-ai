"""`/api/video/projet` — le point d'entree reel de l'orchestrateur Video.

Avant ce fichier, `agents/video/production_agent.py:VideoProductionAgent`
existait, testait vert contre des doubles de ses collaborateurs, mais
n'etait atteint par AUCUN point d'entree reel (`scripts/orphelins.py`,
`docs/CURRENT_TASK.md`) — construit, jamais joignable. C'est le sujet de
ce fichier, et rien de plus : aucune logique d'orchestration n'est ecrite
ici, seulement la route.

Meme controle que `/api/process-video` sur les references : un chemin doit
vivre dans `MEDIA_DIR`, jamais un chemin arbitraire du disque du serveur.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.backend.config import MEDIA_DIR
from apps.backend.runtime import video_production_agent
from apps.backend.security import limiter_debit, verify_api_key

logger = logging.getLogger("usman.backend.video_production")

router = APIRouter()


class ProjetVideoRequest(BaseModel):
    objectif: str
    #: Chemins de fichiers deja sur le disque (MEDIA_DIR) : plans, photos,
    #: rushes. Le modele ne les cite jamais lui-meme, seulement par index —
    #: voir `core/production/plan_video.py:prompt_de_planification`.
    references: List[str] = Field(default_factory=list)
    contraintes: Dict[str, Any] = Field(default_factory=dict)
    #: Mode TEAM : sous-ensemble explicite de capacites. Absent = mode AUTO,
    #: l'agent choisit parmi la liste fermee entiere.
    capacites: Optional[List[str]] = None
    parallelisme: Optional[int] = None
    #: Personnage connu (`core/characters/registry.py`, DEC-0084) : ses
    #: images de reference rejoignent `references`, son profil enrichit le
    #: prompt de planification — voir `VideoProductionAgent.run`.
    personnage_id: Optional[str] = None


def _reference_sure(chemin_brut: str) -> str:
    """Une reference doit vivre dans `MEDIA_DIR` — meme discipline que
    `/api/process-video` (`apps/backend/routers/media.py`)."""
    chemin = Path(chemin_brut).resolve()
    try:
        chemin.relative_to(MEDIA_DIR.resolve())
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=f"Reference hors de MEDIA_DIR : {chemin_brut}") from None
    return str(chemin)


@router.post("/api/video/projet",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def creer_projet_video(request: ProjetVideoRequest) -> Dict[str, Any]:
    references = [_reference_sure(r) for r in request.references]

    contexte: Dict[str, Any] = {"references": references, "contraintes": request.contraintes}
    if request.capacites:
        contexte["capacites"] = request.capacites
    if request.parallelisme:
        contexte["parallelisme"] = request.parallelisme
    if request.personnage_id:
        contexte["personnage_id"] = request.personnage_id

    try:
        return await video_production_agent.run(request.objectif, context=contexte)
    except Exception as erreur:  # noqa: BLE001 — une panne se rapporte, jamais un 500 muet
        logger.error("Projet Video en echec : %s", erreur)
        raise HTTPException(status_code=500, detail=str(erreur)) from erreur
