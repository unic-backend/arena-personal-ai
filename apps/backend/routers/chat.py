"""Conversation et aiguillage vers les agents.

`dispatch_request` est le point ou une demande devient le travail d'un agent
precis. L'intention y est calculee une seule fois : elle coute un appel au
modele.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from apps.backend.config import AGENTS_SPECIALISES, MEDIA_DIR
from apps.backend.prompts import get_arena_system_prompt
from apps.backend.runtime import (
    browser_agent,
    coder_agent,
    editor_agent,
    fast_provider,
    fresh_agent,
    graphrag_tool,
    lightrag_tool,
    memory,
    orchestrator,
    publisher_agent,
    repo_engineer,
    researcher_agent,
    subtitle_agent,
    swe_agent,
    trend_agent,
    video_agent,
)
from apps.backend.security import limiter_debit, validate_media_path, verify_api_key
from apps.backend.studio import lancer_studio

logger = logging.getLogger("arena.backend")

router = APIRouter()


class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = "default"
    video_path: Optional[str] = None
    region: Optional[str] = "Sénégal"


def formater_sources(sources: List[Dict[str, Any]]) -> str:
    """Ajoute la liste des sources sous une reponse, pour les canaux en texte seul.

    Le format OpenAI n'a pas de champ pour des sources : sans cela, le lecteur ne
    saurait pas d'ou vient la reponse.
    """
    if not sources:
        return ""
    lignes = [f"[{s['index']}] {s['title']} — {s['url']}" for s in sources]
    return "\n\n**Sources**\n" + "\n".join(lignes)


async def dispatch_request(request: ChatRequest, intent: Optional[str] = None) -> Dict[str, Any]:
    """Aiguille la demande vers l'agent choisi.

    `intent` permet a l'appelant de transmettre une classification deja faite :
    elle coute un appel au modele, inutile de la refaire.
    """
    session_id = request.session_id or "default"
    if intent is None:
        intent = await orchestrator.analyze_intent(request.prompt)
    logger.info(f"Intention détectée par ARENA: {intent}")

    if intent == "DEEP_REASONING":
        result = await orchestrator.run(request.prompt, context={"session_id": session_id, "intent": intent})
    elif intent == "FRESH_INFO":
        result = await fresh_agent.run(request.prompt)
    elif intent == "STUDIO":
        result = await lancer_studio(video_agent, editor_agent, subtitle_agent)
    elif intent == "BROWSER":
        result = await browser_agent.run(request.prompt)
    elif intent == "SWE_FIX":
        result = await swe_agent.run(request.prompt)
    elif intent == "REPO_ENGINEERING":
        result = await repo_engineer.run(request.prompt)
    elif intent == "RAG_DOCS":
        result = {"response": lightrag_tool.query(request.prompt, mode="hybrid"), "agent": "LightRAG"}
    elif intent == "GRAPHRAG":
        result = graphrag_tool.query_global(request.prompt)
    elif intent == "DEEP_RESEARCH":
        result = await researcher_agent.run(request.prompt)
    elif intent == "CODE_EXECUTION":
        result = await coder_agent.run(request.prompt)
    elif intent == "TREND_SEARCH":
        result = await trend_agent.run(request.prompt, context={"region": request.region})
    elif intent == "VIDEO_ANALYSIS":
        raw_path = request.video_path or str(MEDIA_DIR / "source" / "test_video.mp4")
        v_path = validate_media_path(raw_path)
        result = await video_agent.run(request.prompt, context={"video_path": str(v_path)})
    elif "PUBLI" in request.prompt.upper() or "POSTER" in request.prompt.upper():
        result = await publisher_agent.run(request.prompt, context={"video_path": request.video_path})
    else:
        result = await orchestrator.run(
            user_input=request.prompt,
            context={"session_id": session_id, "intent": intent},
        )

    # L'aiguilleur sait quelle branche il a prise ; sans cela, la reponse annoncait
    # « CHAT » meme quand un agent specialise avait repondu.
    result["intent"] = intent

    memory.add_chat_message(session_id=session_id, role="user", content=request.prompt)
    memory.add_chat_message(session_id=session_id, role="assistant", content=result["response"])
    return result

@router.post("/api/chat", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def chat_endpoint(request: ChatRequest):
    try:
        if not await fast_provider.is_available():
            return {"status": "error", "model": fast_provider.model_name, "response": "❌ Ollama hors-ligne."}

        result = await dispatch_request(request)
        return {
            "status": "success",
            "model": fast_provider.model_name,
            "intent": result.get("intent", "CHAT"),
            "agent": result.get("agent", "OrchestratorAgent"),
            "sources": result.get("sources", []),
            "response": result["response"]
        }
    except Exception as e:
        logger.error(f"Erreur endpoint chat: {e}", exc_info=True)
        return {"status": "error", "model": "error", "response": f"❌ {str(e)}"}

@router.post("/api/chat/stream", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def chat_stream_endpoint(request: ChatRequest):
    session_id = request.session_id or "default"
    intent = await orchestrator.analyze_intent(request.prompt)

    if intent in AGENTS_SPECIALISES:
        result = await dispatch_request(request, intent=intent)
        async def text_gen():
            yield f"data: {json.dumps({'token': result['response'], 'intent': intent})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(text_gen(), media_type="text/event-stream")
    else:
        history = memory.get_recent_history(session_id=session_id, limit=6)
        memory.add_chat_message(session_id=session_id, role="user", content=request.prompt)

        system_prompt = get_arena_system_prompt()

        prompt_lines = []
        for msg in history:
            role_label = memory.get_fact("owner") or "Saer" if msg["role"] == "user" else "ARENA"
            prompt_lines.append(f"{role_label}: {msg['content']}")
        prompt_lines.append(f"{memory.get_fact('owner') or 'Saer'}: {request.prompt}")
        prompt_lines.append("ARENA:")
        full_prompt = "\n".join(prompt_lines)

        async def token_generator():
            full_reply = ""
            async for token in fast_provider.generate_stream(full_prompt, system_prompt):
                full_reply += token
                yield f"data: {json.dumps({'token': token, 'intent': intent})}\n\n"

            memory.add_chat_message(session_id=session_id, role="assistant", content=full_reply.strip())
            yield "data: [DONE]\n\n"

        return StreamingResponse(token_generator(), media_type="text/event-stream")
