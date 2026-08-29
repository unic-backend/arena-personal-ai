"""Le gardien, exposé — infrastructure, pas un chatbot.

Deux routes, protégées comme `/api/observability` (même clé, même
limiteur) : `GET` lit l'état sans rien lancer, `POST` déclenche un cycle
réel (diagnostics + mise à jour de la file). Ni l'une ni l'autre n'écrit du
code applicatif — voir `core/guardian/gardien.py` sur la limite volontaire
de ce premier étage.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends

from apps.backend.runtime import file_maintenance, gardien
from apps.backend.security import limiter_debit, verify_api_key

logger = logging.getLogger("usman.backend.gardien")

router = APIRouter()


@router.get("/api/gardien/rapport",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_rapport() -> Dict[str, Any]:
    """Ce que la file de maintenance contient déjà — sans lancer de cycle."""
    ouvertes = file_maintenance.ouvertes()
    par_categorie: Dict[str, int] = {}
    for tache in ouvertes:
        par_categorie[tache.categorie] = par_categorie.get(tache.categorie, 0) + 1
    return {
        "total_ouvertes": len(ouvertes),
        "ouvertes_par_categorie": par_categorie,
        "taches_ouvertes": [t.to_dict() for t in ouvertes[:10]],
    }


@router.post("/api/gardien/cycle",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lancer_cycle() -> Dict[str, Any]:
    """Lance un cycle réel : ruff + pytest + orphelins, puis met la file à jour.

    Peut prendre plusieurs dizaines de secondes (la suite de tests tourne
    en entier) — c'est un déclenchement explicite, jamais une boucle qui
    tourne sur le chemin d'une conversation.
    """
    logger.info("Cycle du gardien declenche via l'API.")
    rapport = gardien.executer_cycle()
    return rapport.to_dict()
