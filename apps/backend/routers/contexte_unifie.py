"""`/api/contexte/rechercher` — la recherche unifiée (code, mémoire,
internet), réellement atteignable.

Pas d'aiguillage depuis le chat (même choix que `/api/hermes-evolution/
evoluer`, `/api/video/projet`) : un outil de développement/diagnostic,
appelé explicitement — `core/context/recherche_unifiee.py` reste composable
depuis n'importe quel agent qui l'importerait directement, cette route
n'est que le premier appelant réel, jamais le seul chemin possible.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.backend import BASE_DIR
from apps.backend.runtime import fresh_agent, registre
from apps.backend.security import limiter_debit, verify_api_key
from core.context.recherche_unifiee import rechercher_unifie

logger = logging.getLogger("usman.backend.contexte_unifie")

router = APIRouter()


class RechercheUnifieeRequest(BaseModel):
    question: str
    #: Le dossier à interroger via Claude Context — le dépôt d'ARENA
    #: lui-même par défaut ("USMAN CODER"), un autre projet sur demande.
    chemin_code: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/api/contexte/rechercher",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def rechercher(request: RechercheUnifieeRequest) -> Dict[str, Any]:
    return await rechercher_unifie(
        request.question,
        registre=registre,
        fresh_info_agent=fresh_agent,
        chemin_code=request.chemin_code or str(BASE_DIR),
        session_id=request.session_id,
    )
