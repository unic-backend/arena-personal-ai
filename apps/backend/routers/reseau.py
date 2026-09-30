"""La sante reseau d'ARENA, exposee — infrastructure, pas un chatbot.

Une seule route, protegee comme `/api/observability` et `/api/gardien/rapport`
(meme cle, meme limiteur) : `GET` lit la sante reseau sans lancer de test de
debit. Elle passe par l'adaptateur `core/reseau/sante_reseau.py`, qui choisit
Netronome quand il est branche et retombe sur la sonde native d'ARENA sinon —
le chemin ne connait donc jamais Netronome directement.

Le test de debit (`mesurer_debit`, couteux) n'est PAS ici : il passe par la
confirmation du connecteur, jamais par une route en lecture.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends

from apps.backend.runtime import registre
from apps.backend.security import limiter_debit, verify_api_key
from core.reseau.sante_reseau import evaluer_sante_reseau

logger = logging.getLogger("usman.backend.reseau")

router = APIRouter()


@router.get("/api/reseau/sante",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_sante_reseau() -> Dict[str, Any]:
    """La sante reseau connue, sans lancer de test de debit.

    Netronome branche -> mesures completes (debit, latence, perte, DNS).
    Netronome absent -> sonde native ARENA (connectivite + DNS), le reste
    reste `None`. Le statut dit toujours laquelle des deux sources a repondu.
    """
    return evaluer_sante_reseau(registre).to_dict()
