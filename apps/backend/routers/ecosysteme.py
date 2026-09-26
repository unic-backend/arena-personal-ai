"""L'ecosysteme d'agents, expose a la PWA et aux clients (DEC-0146).

Quatre routes, aucune liste d'agents : tout vient du registre que la
decouverte a rempli (`apps/backend/runtime.py::collaborateurs`).

- `GET  /api/agents` : les fiches de TOUS les agents presents.
- `POST /api/agents/table-ronde` : une table ronde sur un probleme.
- `POST /api/agents/projet` : un projet decoupe, reparti, execute, synthetise.
- `GET  /api/agents/espaces/{project_id}` : l'espace de travail partage.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.backend.runtime import collaborateurs
from apps.backend.security import limiter_debit, verify_api_key
from core.agent.collaboration import PARTICIPANTS_MAX, TOURS, conduire_projet, tenir_table_ronde
from core.agent.espace_de_travail import ESPACES

router = APIRouter()

_PROTECTIONS = [Depends(verify_api_key), Depends(limiter_debit)]


class DemandeTableRonde(BaseModel):
    probleme: str = Field(..., min_length=3, max_length=4000)
    participants_max: int = Field(PARTICIPANTS_MAX, ge=2, le=10)
    tours: int = Field(TOURS, ge=1, le=4)
    project_id: Optional[str] = Field(None, max_length=120)


class DemandeProjet(BaseModel):
    projet: str = Field(..., min_length=3, max_length=4000)
    project_id: Optional[str] = Field(None, max_length=120)


@router.get("/api/agents", dependencies=_PROTECTIONS)
def lister_les_agents() -> Dict[str, Any]:
    """Les fiches de tous les agents de l'ecosysteme, telles que lues sur eux."""
    fiches = [fiche.en_dict() for fiche in collaborateurs.fiches()]
    return {"total": len(fiches), "agents": fiches}


@router.post("/api/agents/table-ronde", dependencies=_PROTECTIONS)
async def table_ronde(demande: DemandeTableRonde) -> Dict[str, Any]:
    try:
        table = await tenir_table_ronde(
            collaborateurs, demande.probleme, participants_max=demande.participants_max,
            tours=demande.tours, project_id=demande.project_id or "")
    except LookupError as erreur:
        raise HTTPException(status_code=503, detail=str(erreur)) from erreur
    return table.en_dict()


@router.post("/api/agents/projet", dependencies=_PROTECTIONS)
async def projet(demande: DemandeProjet) -> Dict[str, Any]:
    try:
        return await conduire_projet(collaborateurs, demande.projet,
                                     project_id=demande.project_id or "")
    except LookupError as erreur:
        raise HTTPException(status_code=503, detail=str(erreur)) from erreur


@router.get("/api/agents/espaces/{project_id}", dependencies=_PROTECTIONS)
def espace(project_id: str) -> Dict[str, Any]:
    if not ESPACES.existe(project_id):
        raise HTTPException(status_code=404, detail=f"Aucun espace pour le projet {project_id}.")
    return ESPACES.pour(project_id).etat()
