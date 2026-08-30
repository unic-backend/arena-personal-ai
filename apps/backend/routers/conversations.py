"""Les conversations, partagees entre ses appareils.

Deux routes, protegees comme le reste de la passerelle (meme cle, meme
limiteur) :

- `GET  /conversations`      — tout ce que le coffre contient, pour un appareil
                               qui arrive vide ;
- `POST /conversations/sync` — l'appareil envoie les siennes et recoit en retour
                               la verite du serveur, deja fusionnee.

Un seul aller-retour pour la synchronisation, volontairement : deux appels
(pousser puis tirer) laissent une fenetre ou l'appareil a envoye sans avoir
recu, et c'est dans cette fenetre que naissent les doublons.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from apps.backend.runtime import depot_conversations
from apps.backend.security import limiter_debit, verify_api_key

logger = logging.getLogger("usman.backend.conversations")

router = APIRouter()


class DemandeSync(BaseModel):
    """Ce que l'appareil envoie : ses conversations, telles qu'il les a."""

    conversations: List[Dict[str, Any]] = Field(default_factory=list)
    #: Facultatif : ne rendre que ce qui a change depuis cette date (ms).
    depuis: Optional[int] = None


@router.get("/conversations",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_conversations(depuis: Optional[int] = None) -> Dict[str, Any]:
    """Tout ce que le coffre contient — pierres tombales comprises."""
    conversations = depot_conversations.lister(depuis)
    return {"conversations": conversations, "total": depot_conversations.compter()}


@router.post("/conversations/sync",
             dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def synchroniser(demande: DemandeSync) -> Dict[str, Any]:
    """Recoit les conversations d'un appareil, rend la verite fusionnee.

    `refusees` n'est jamais tu : une conversation trop grosse est ecartee, et
    l'appareil doit pouvoir le dire a son proprietaire plutot que de croire
    qu'elle est en sureté.
    """
    ecrites, refusees = depot_conversations.deposer(demande.conversations)
    if refusees:
        logger.warning("%d conversation(s) refusee(s) a la synchronisation.", len(refusees))
    return {
        "conversations": depot_conversations.lister(demande.depuis),
        "ecrites": ecrites,
        "refusees": refusees,
        "total": depot_conversations.compter(),
    }
