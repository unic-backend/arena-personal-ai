"""`/api/personnages` — identite persistante de personnage, et son pipeline
de generation (mission ARENA x AGENT HEROES, DEC-0084).

Meme discipline que `video_production.py` : aucune logique d'orchestration
ici, seulement la route. La creation/lecture passe par
`core/characters/registry.py` ; la generation passe par
`VideoProductionAgent.generer_image_personnage`/`appliquer_identite_personnage`
(donc par la meme file de confirmation que tout le reste de la Video).
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.backend.runtime import video_production_agent
from apps.backend.security import limiter_debit, validate_media_path, verify_api_key
from core.characters.registry import Personnage, charger_personnage, charger_registre, creer_personnage

logger = logging.getLogger("usman.backend.personnages")

router = APIRouter()


class CreerPersonnageRequest(BaseModel):
    nom: str
    description: str = ""
    #: Chemins deja dans MEDIA_DIR — jamais uploades ici (meme discipline
    #: que les references de `/api/video/projet`) : l'upload existe deja
    #: ailleurs (`/api/process-video` et consorts), ce module ne le refait pas.
    images_reference: List[str] = Field(default_factory=list)
    profil_visuel: str
    negatif: str = ""
    profil_voix: Optional[str] = None


class GenererImageRequest(BaseModel):
    description_scene: str


class AppliquerIdentiteRequest(BaseModel):
    fichier_cible: str
    many_faces: bool = False


def _personnage_ou_404(identifiant: str) -> Personnage:
    personnage = charger_personnage(identifiant)
    if personnage is None:
        raise HTTPException(status_code=404, detail=f"Personnage inconnu : {identifiant}")
    return personnage


@router.post("/api/personnages",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def creer(request: CreerPersonnageRequest) -> Dict[str, Any]:
    images = [str(validate_media_path(chemin)) for chemin in request.images_reference]
    try:
        personnage = creer_personnage(
            request.nom, request.description, images, request.profil_visuel,
            negatif=request.negatif, profil_voix=request.profil_voix)
    except ValueError as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from erreur
    return personnage.to_dict()


@router.get("/api/personnages",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lister() -> List[Dict[str, Any]]:
    return [p.to_dict() for p in charger_registre()]


@router.get("/api/personnages/{identifiant}",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def obtenir(identifiant: str) -> Dict[str, Any]:
    return _personnage_ou_404(identifiant).to_dict()


@router.post("/api/personnages/{identifiant}/image",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def generer_image(identifiant: str, request: GenererImageRequest) -> Dict[str, Any]:
    _personnage_ou_404(identifiant)  # 404 avant de solliciter WanGP
    try:
        return await video_production_agent.generer_image_personnage(
            identifiant, request.description_scene)
    except Exception as erreur:  # noqa: BLE001 — une panne se rapporte, jamais un 500 muet
        logger.error("Generation personnage %s en echec : %s", identifiant, erreur)
        raise HTTPException(status_code=500, detail=str(erreur)) from erreur


@router.post("/api/personnages/{identifiant}/identite",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def appliquer_identite(identifiant: str, request: AppliquerIdentiteRequest) -> Dict[str, Any]:
    _personnage_ou_404(identifiant)
    fichier_cible = str(validate_media_path(request.fichier_cible))
    try:
        return await video_production_agent.appliquer_identite_personnage(
            identifiant, fichier_cible, many_faces=request.many_faces)
    except Exception as erreur:  # noqa: BLE001
        logger.error("Application identite %s en echec : %s", identifiant, erreur)
        raise HTTPException(status_code=500, detail=str(erreur)) from erreur
