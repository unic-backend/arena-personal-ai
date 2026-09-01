"""Passerelle compatible OpenAI.

C'est la decision d'architecture la plus rentable du projet : n'importe quel
client concu pour parler a ChatGPT parle a Usman en changeant l'adresse du
serveur. Chaque « modele » expose ici est en realite un agent.
"""

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from apps.backend.config import AGENTS_SPECIALISES
from apps.backend.prompts import get_arena_system_prompt
from apps.backend.routers.chat import ChatRequest, dispatch_request, formater_sources
from apps.backend.runtime import (
    browser_agent,
    coder_agent,
    editor_agent,
    fast_provider,
    fresh_agent,
    graphrag_tool,
    lightrag_tool,
    orchestrator,
    plaquiste_agent,
    repo_engineer,
    researcher_agent,
    subtitle_agent,
    swe_agent,
    video_agent,
)
from apps.backend.security import limiter_debit, verify_api_key
from apps.backend.studio import lancer_studio

logger = logging.getLogger("usman.backend")

router = APIRouter()


# Le projet s appelle Usman depuis le 2026-08-26. Les conversations deja
# ouvertes dans LibreChat portent encore les anciens identifiants dans leur
# historique : les refuser afficherait une erreur sur des echanges qui
# marchaient hier. Ils sont donc traduits, pas rejetes.
ANCIENS_NOMS = {
    "arena-core": "usman-chat",
    "arena-coder": "usman-coder",
    "arena-video": "usman-video",
    "arena-studio": "usman-studio",
    "arena-fresh": "usman-fresh",
    "arena-deep-research": "usman-research",
    "arena-swe-agent": "usman-fix",
    "arena-repo-engineer": "usman-repo",
    "arena-browser": "usman-browser",
    "arena-rag-docs": "usman-docs",
    "arena-graphrag": "usman-graph",
}


# ==============================================================================
# ENDPOINTS COMPATIBLES OPENAI (LibreChat / Open WebUI)
# ==============================================================================
@router.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_openai_models():
    return {
        "object": "list",
        "data": [
            {"id": "usman-chat", "object": "model", "owned_by": "arena"},
            {"id": "usman-coder", "object": "model", "owned_by": "arena"},
            {"id": "usman-fix", "object": "model", "owned_by": "arena"},
            {"id": "usman-repo", "object": "model", "owned_by": "arena"},
            {"id": "usman-research", "object": "model", "owned_by": "arena"},
            {"id": "usman-fresh", "object": "model", "owned_by": "arena"},
            {"id": "usman-docs", "object": "model", "owned_by": "arena"},
            {"id": "usman-graph", "object": "model", "owned_by": "arena"},
            {"id": "usman-browser", "object": "model", "owned_by": "arena"},
            {"id": "usman-video", "object": "model", "owned_by": "arena"},
            {"id": "usman-plaquiste", "object": "model", "owned_by": "arena"},
            {"id": "usman-studio", "object": "model", "owned_by": "arena"}
        ]
    }

def garantir_un_texte(contenu: str, modele: str) -> str:
    """Empêche qu'une réponse vide parte comme si c'était une réponse.

    Chaque branche d'aiguillage lit `.get("response", "")`. Un agent qui échoue
    renvoie un dictionnaire sans cette clé, donc la chaîne vide — et `"" is not
    None` est vrai. LibreChat affichait alors **une bulle entièrement vide**,
    sans texte ni erreur. Observé le 2026-08-26 sur `usman-research`.

    Une capacité qui n'a rien produit dit qu'elle n'a rien produit. C'est la
    règle appliquée partout ailleurs dans ce dépôt ; elle manquait ici.
    """
    if contenu and contenu.strip():
        return contenu

    logger.warning(f"Modele '{modele}' n'a produit aucun texte")
    return (
        f"`{modele}` n'a produit aucune réponse.\n\n"
        "Ce n'est pas un refus : l'agent s'est arrêté sans rien renvoyer. "
        "Les journaux du serveur Usman disent à quelle étape. "
        "Reformule la demande, ou choisis `usman-chat`."
    )


#: 503 et non 500 : le probleme n'est pas la requete, et un client qui
#: reessaie plus tard a raison de le faire.
CODE_SERVICE_INDISPONIBLE = 503


def _erreur_openai(souci: Exception, modele: str, stream: bool):
    """L'erreur, dans la forme qu'un client compatible OpenAI sait lire.

    Sans elle, une panne d'Ollama sortait en `500 Internal Server Error`,
    `text/plain`, corps vide — sur la surface que les outils EXTERIEURS
    utilisent. Le client ne pouvait pas distinguer « le service est tombe »
    de « ta requete est invalide » (mesure du 01/09/2026). `/api/chat`
    disait deja « Ollama hors-ligne » proprement ; cette passerelle non.
    """
    message = f"ARENA n'a pas pu repondre : {souci}"
    logger.error("Passerelle OpenAI interrompue : %s", souci, exc_info=True)

    if stream:
        async def generateur():
            cree = int(time.time())
            yield "data: " + json.dumps({
                "id": f"chatcmpl-{cree}", "object": "chat.completion.chunk",
                "created": cree, "model": modele,
                "choices": [{"index": 0, "delta": {"content": message},
                             "finish_reason": "stop"}],
                "error": {"message": message, "type": "service_unavailable"},
            }) + "\n\n"
            # `[DONE]` meme en erreur : sans lui, le client attend indefiniment.
            yield "data: [DONE]\n\n"
        return StreamingResponse(generateur(), media_type="text/event-stream")

    return JSONResponse(
        status_code=CODE_SERVICE_INDISPONIBLE,
        content={"error": {"message": message, "type": "service_unavailable",
                           "code": "provider_unavailable"}})


def _reponse_openai(contenu: str, modele: str, stream: bool):
    """Emballe une reponse au format attendu par OpenAI (streamee ou non)."""
    cree = int(time.time())

    if stream:
        async def generateur():
            morceau = {
                "id": f"chatcmpl-{cree}",
                "object": "chat.completion.chunk",
                "created": cree,
                "model": modele,
                "choices": [{"index": 0, "delta": {"content": contenu}, "finish_reason": "stop"}]
            }
            yield f"data: {json.dumps(morceau)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(generateur(), media_type="text/event-stream")

    return {
        "id": f"chatcmpl-{cree}",
        "object": "chat.completion",
        "created": cree,
        "model": modele,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": contenu},
            "finish_reason": "stop"
        }]
    }


@router.post("/v1/chat/completions", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def openai_chat_completions(request: Request):
    """Point d'entree compatible OpenAI — il repond toujours quelque chose.

    `HTTPException` traverse intacte : un refus d'authentification ou de
    quota n'est pas une panne de service et ne doit pas etre maquille en
    503.
    """
    body = await request.json()
    stream = bool(body.get("stream", False))
    model_requested = body.get("model", "usman-chat")
    try:
        return await _repondre(body, stream, model_requested)
    except HTTPException:
        raise
    except Exception as souci:  # noqa: BLE001 - la passerelle repond toujours
        return _erreur_openai(souci, model_requested, stream)


async def _repondre(body: dict, stream: bool, model_requested: str):
    """Le travail reel, sorti pour qu'un seul `try` le couvre en entier."""
    messages = body.get("messages", [])

    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break
    if not last_user_msg:
        last_user_msg = "Bonjour"

    chat_req = ChatRequest(prompt=last_user_msg)

    # ---- Agents joignables directement par leur nom dans le menu ----
    contenu = None

    if model_requested == "usman-fix":
        contenu = (await swe_agent.run(last_user_msg)).get("response", "")

    elif model_requested == "usman-repo":
        contenu = (await repo_engineer.run(last_user_msg)).get("response", "")

    elif model_requested == "usman-coder":
        contenu = (await coder_agent.run(last_user_msg)).get("response", "")

    elif model_requested == "usman-research":
        contenu = (await researcher_agent.run(last_user_msg)).get("response", "")

    elif model_requested == "usman-fresh":
        res = await fresh_agent.run(last_user_msg)
        contenu = res.get("response", "") + formater_sources(res.get("sources", []), last_user_msg)

    elif model_requested == "usman-plaquiste":
        contenu = (await plaquiste_agent.run(last_user_msg)).get("response", "")

    elif model_requested == "usman-browser":
        contenu = (await browser_agent.run(last_user_msg)).get("response", "")

    elif model_requested in ("usman-video", "usman-studio"):
        # « usman-video » est le nom propose dans le menu ; « usman-studio »
        # reste accepte pour ne casser aucun client deja configure avec lui.
        contenu = (await lancer_studio(video_agent, editor_agent, subtitle_agent)).get("response", "")

    elif model_requested == "usman-graph":
        contenu = graphrag_tool.query_global(last_user_msg).get("response", "")

    elif model_requested == "usman-docs":
        contenu = lightrag_tool.query(last_user_msg, mode="hybrid")

    if contenu is not None:
        logger.info(f"Modele '{model_requested}' -> agent dedie")
        return _reponse_openai(garantir_un_texte(contenu, model_requested), model_requested, stream)

    # ---- usman-chat : aiguillage automatique selon la question ----
    intent = await orchestrator.analyze_intent(last_user_msg)
    logger.info(f"Modele 'usman-chat' -> intention detectee : {intent}")

    if intent in AGENTS_SPECIALISES:
        res = await dispatch_request(chat_req, intent=intent)
        contenu = res.get("response", "") + formater_sources(res.get("sources", []), last_user_msg)
        return _reponse_openai(garantir_un_texte(contenu, intent), model_requested, stream)

    # ---- Discussion simple : reponse mot par mot ----
    if not stream:
        res = await dispatch_request(chat_req, intent=intent)
        return _reponse_openai(garantir_un_texte(res.get("response", ""), intent), model_requested, stream)

    async def generateur_discussion():
        cree = int(time.time())
        system_prompt = get_arena_system_prompt()

        try:
            async for jeton in fast_provider.generate_stream(last_user_msg, system_prompt):
                morceau = {
                    "id": f"chatcmpl-{cree}",
                    "object": "chat.completion.chunk",
                    "created": cree,
                    "model": model_requested,
                    "choices": [{"index": 0, "delta": {"content": jeton}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(morceau)}\n\n"
        except Exception as souci:  # noqa: BLE001 - le flux doit finir proprement
            # Meme defaut que `/api/chat/stream` avant le 01/09/2026 : une
            # panne en cours de flux rendait un `200` et zero ligne.
            logger.error("Flux OpenAI interrompu : %s", souci, exc_info=True)
            yield "data: " + json.dumps({
                "id": f"chatcmpl-{cree}", "object": "chat.completion.chunk",
                "created": cree, "model": model_requested,
                "choices": [{"index": 0,
                             "delta": {"content": f"ARENA n'a pas pu terminer : {souci}"},
                             "finish_reason": "stop"}],
                "error": {"message": str(souci), "type": "service_unavailable"},
            }) + "\n\n"
            yield "data: [DONE]\n\n"
            return

        fin = {
            "id": f"chatcmpl-{cree}",
            "object": "chat.completion.chunk",
            "created": cree,
            "model": model_requested,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        }
        yield f"data: {json.dumps(fin)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generateur_discussion(), media_type="text/event-stream")
