"""Passerelle vers l'interface PWA du proprietaire.

Son application React parle un protocole precis, deja ecrit et deja teste chez
lui. Deux facons de les relier existaient : reecrire son `remoteTransport.ts`
pour appeler les routes d'ARENA, ou apprendre a ARENA le langage que son app
parle. **C'est la seconde qui est retenue.**

Pourquoi : son interface fonctionne ; la casser pour l'adapter serait payer en
risque ce qu'on gagne en confort. Et le depot connait deja ce motif —
`openai_gateway.py` fait exactement cela pour LibreChat.

Le protocole, releve dans son code (`src/lib/activity/`) :

- `POST /agent/stream` — corps JSON `{text, locale, history, attachments,
  connectors, run_id, persona, memories}`, reponse en `text/event-stream`.
- Chaque trame est `data: <json>` suivie d'une ligne vide. Le JSON vaut
  `{"type":"token","text":...}`, `{"type":"done","meta":...}` ou
  `{"type":"error","message":...}`.
- **Le flux doit se terminer par `done` ou par `error`.** Son client considere
  une fermeture sans l'un des deux comme une coupure et relance la requete —
  jusqu'a trois fois. Un flux qui s'arrete en silence devient trois reponses.

**Ce qui n'est pas applique, et n'est pas fait semblant d'etre applique :**
`persona`, `memories`, `connectors` et `attachments` arrivent dans la requete et
ne sont pas encore utilises. Ils sont journalises, jamais ignores en silence :
une interface qui offre un reglage sans effet est pire qu'une interface qui ne
l'offre pas. `POST /files` le declare franchement plutot que d'accepter un
fichier qui n'irait nulle part.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.backend.config import AGENTS_SPECIALISES
from apps.backend.prompts import get_arena_system_prompt
from apps.backend.routers.chat import ChatRequest, dispatch_request
from apps.backend.runtime import fast_provider, memory, orchestrator
from apps.backend.security import limiter_debit, verify_api_key

logger = logging.getLogger("usman.backend.pwa")

router = APIRouter()

# Champs que l'interface envoie et qu'ARENA ne sait pas encore honorer. Ecrits
# ici pour que le journal les nomme un par un, plutot qu'un vague « ignore ».
CHAMPS_NON_APPLIQUES = ("persona", "memories", "connectors", "attachments")


class DemandeAgent(BaseModel):
    """Le corps envoye par `remoteTransport.ts`.

    Tous les champs sauf `text` sont facultatifs : l'interface peut evoluer sans
    que la passerelle refuse une requete pour un champ qu'elle ne connait pas.
    """

    text: str
    locale: Optional[str] = None
    history: List[Dict[str, str]] = Field(default_factory=list)
    attachments: List[str] = Field(default_factory=list)
    connectors: Any = None
    run_id: Optional[str] = None
    persona: Optional[Dict[str, Any]] = None
    memories: Any = None


def trame(charge: Dict[str, Any]) -> str:
    """Une trame SSE : `data: <json>` puis une ligne vide."""
    return f"data: {json.dumps(charge, ensure_ascii=False)}\n\n"


def jeton(texte: str) -> str:
    return trame({"type": "token", "text": texte})


def fin(meta: Optional[Dict[str, Any]] = None) -> str:
    """La trame que son client attend pour savoir que c'est fini."""
    return trame({"type": "done", "meta": meta or {}})


def erreur(message: str) -> str:
    return trame({"type": "error", "message": message})


def _signaler_non_applique(demande: DemandeAgent) -> None:
    """Journalise ce que la requete portait et qu'ARENA n'utilise pas encore."""
    presents = [
        nom for nom in CHAMPS_NON_APPLIQUES
        if getattr(demande, nom, None) not in (None, [], {}, "")
    ]
    if presents:
        logger.info(
            "PWA : champs recus et non appliques -> %s. Ils ne sont pas perdus, "
            "ils ne sont pas encore honores.", ", ".join(presents),
        )


def _prompt_conversation(demande: DemandeAgent, proprietaire: str) -> str:
    """Reconstruit le fil a partir de l'historique envoye par l'interface.

    L'historique vient du navigateur : c'est lui qui fait foi pour cette
    conversation-la. La memoire d'ARENA garde sa propre trace en parallele.
    """
    lignes = [
        f"{proprietaire if tour.get('role') == 'user' else 'Usman'}: {tour.get('content', '')}"
        for tour in demande.history
    ]
    lignes.append(f"{proprietaire}: {demande.text}")
    lignes.append("Usman:")
    return "\n".join(lignes)


@router.post("/agent/stream", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def flux_agent(demande: DemandeAgent):
    """Repond a l'interface PWA, en direct, dans son protocole.

    Le flux se termine **toujours** par `done` ou `error` : sans cela son client
    relance la requete jusqu'a trois fois, et une reponse devient trois.
    """
    _signaler_non_applique(demande)
    session = demande.run_id or "pwa"
    proprietaire = memory.get_fact("owner") or "Ousmane"

    async def flux():
        try:
            if not await fast_provider.is_available():
                yield erreur(
                    "Ollama est hors-ligne. Demarre-le (ollama serve) : ARENA ne "
                    "fabrique pas de reponse sans son modele."
                )
                return

            intention = await orchestrator.analyze_intent(demande.text)

            # Un agent specialise rend une reponse complete, pas un flux. On la
            # rend d'un bloc plutot que de la decouper en faux jetons.
            if intention in AGENTS_SPECIALISES:
                resultat = await dispatch_request(
                    ChatRequest(prompt=demande.text, session_id=session), intent=intention
                )
                yield jeton(resultat["response"])
                yield fin({
                    "provider": "arena",
                    "model": fast_provider.model_name,
                    "sources": resultat.get("sources", []),
                    "query": intention,
                })
                return

            memory.add_chat_message(session_id=session, role="user", content=demande.text)
            complet = ""
            async for morceau in fast_provider.generate_stream(
                _prompt_conversation(demande, proprietaire), get_arena_system_prompt()
            ):
                complet += morceau
                yield jeton(morceau)

            memory.add_chat_message(
                session_id=session, role="assistant", content=complet.strip()
            )
            yield fin({
                "provider": "arena",
                "model": fast_provider.model_name,
                "query": intention,
            })

        except Exception as souci:  # noqa: BLE001 - le flux doit finir proprement
            logger.error("Flux PWA interrompu : %s", souci, exc_info=True)
            yield erreur(f"ARENA n'a pas pu terminer : {souci}")

    return StreamingResponse(flux(), media_type="text/event-stream")


@router.post("/files", dependencies=[Depends(verify_api_key)])
async def envoyer_fichiers():
    """Declare que les pieces jointes ne sont pas traitees ici.

    Son interface televerse les fichiers avant d'envoyer le message. ARENA n'a
    pas encore de chaine qui les lit. Accepter le fichier et rendre un
    identifiant donnerait une piece jointe que rien ne lira — c'est la forme la
    plus discrete du mensonge : ca marche, et ca ne fait rien.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Les pieces jointes ne sont pas encore traitees par ARENA. Rien n'a "
            "ete enregistre. Envoie ton message sans fichier en attendant."
        ),
    )
