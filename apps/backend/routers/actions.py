"""La chronologie des actions, en lecture seule.

Un journal que personne ne peut lire est exactement le defaut qu'il vient
corriger : la table `agent_logs` existait depuis le premier jour et rien ne
l'ecrivait *ni* ne la lisait. Cette route est donc livree avec le journal, pas
apres lui.

Lecture seule, volontairement. Confirmer ou annuler une action est un tout autre
geste, avec ses propres garde-fous — chapitre 5 du VOLET.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from apps.backend.runtime import journal
from apps.backend.security import limiter_debit, verify_api_key
from core.actions.timeline import to_dict

logger = logging.getLogger("usman.backend")

router = APIRouter()

# Une chronologie n'est pas un export : au-dela, on pagine plutot que de tout
# charger en memoire.
LIMITE_MAX = 500


@router.get("/api/actions", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_chronologie(
    limite: int = Query(50, ge=1, le=LIMITE_MAX),
    cible: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Rend les actions les plus recentes, resume compris.

    Un journal vide rend un resume a zero et une liste vide — jamais une erreur.
    « Rien ne s'est passe » est une reponse, pas une panne.
    """
    return to_dict(journal.dernieres(limite=limite, cible=cible))
