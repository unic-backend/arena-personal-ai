import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apps.backend.config import (
    AGENTS_SPECIALISES,
    ALLOWED_ORIGINS,
    BASE_DIR,
    EXTENSIONS_MEDIA_AUTORISEES,
    MEDIA_DIR,
    RENDERED_DIR,
    TAILLE_BLOC_ENVOI,
    TAILLE_MAX_ENVOI,
)
from apps.backend.prompts import get_arena_system_prompt
from apps.backend.runtime import (
    browser_agent,
    clip_selector,
    coder_agent,
    deep_provider,
    editor_agent,
    fast_provider,
    fresh_agent,
    graphrag_tool,
    lightrag_tool,
    memory,
    orchestrator,
    permissions,
    publisher_agent,
    repo_engineer,
    researcher_agent,
    subtitle_agent,
    swe_agent,
    trend_agent,
    video_agent,
)
from apps.backend.security import (
    limiter_debit,
    validate_media_path,
    verify_api_key,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arena.backend")

app = FastAPI(title="ARENA Personal AI API", version="1.7.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

RENDERED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/rendered", StaticFiles(directory=str(RENDERED_DIR)), name="rendered")


class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = "default"
    video_path: Optional[str] = None
    region: Optional[str] = "Sénégal"

@app.get("/")
async def serve_frontend():
    return FileResponse(str(BASE_DIR / "apps" / "frontend" / "index.html"))

@app.get("/health")
async def health_check():
    ollama_online = await fast_provider.is_available()
    return {
        "status": "healthy" if ollama_online else "degraded",
        "ollama_available": ollama_online,
        "models": [fast_provider.model_name, deep_provider.model_name],
        "agents_active": [
            "Orchestrator", "ReasoningEngine", "CoderAgent", "RepoEngineerAgent",
            "SWEAgent", "DeepResearcher", "TrendAnalyzer", "VideoAnalyzer",
            "Editor", "Subtitle", "ClipSelector", "Publisher", "BrowserAgent",
            "LightRAG", "MicrosoftGraphRAG"
        ]
    }

# ==============================================================================
# ENDPOINTS COMPATIBLES OPENAI (LibreChat / Open WebUI)
# ==============================================================================
@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_openai_models():
    return {
        "object": "list",
        "data": [
            {"id": "arena-core", "object": "model", "owned_by": "arena"},
            {"id": "arena-coder", "object": "model", "owned_by": "arena"},
            {"id": "arena-swe-agent", "object": "model", "owned_by": "arena"},
            {"id": "arena-repo-engineer", "object": "model", "owned_by": "arena"},
            {"id": "arena-deep-research", "object": "model", "owned_by": "arena"},
            {"id": "arena-fresh", "object": "model", "owned_by": "arena"},
            {"id": "arena-rag-docs", "object": "model", "owned_by": "arena"},
            {"id": "arena-graphrag", "object": "model", "owned_by": "arena"},
            {"id": "arena-browser", "object": "model", "owned_by": "arena"}
        ]
    }

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


@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def openai_chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    model_requested = body.get("model", "arena-core")

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

    if model_requested == "arena-swe-agent":
        contenu = (await swe_agent.run(last_user_msg)).get("response", "")

    elif model_requested == "arena-repo-engineer":
        contenu = (await repo_engineer.run(last_user_msg)).get("response", "")

    elif model_requested == "arena-coder":
        contenu = (await coder_agent.run(last_user_msg)).get("response", "")

    elif model_requested == "arena-deep-research":
        contenu = (await researcher_agent.run(last_user_msg)).get("response", "")

    elif model_requested == "arena-fresh":
        res = await fresh_agent.run(last_user_msg)
        contenu = res.get("response", "") + formater_sources(res.get("sources", []))

    elif model_requested == "arena-browser":
        contenu = (await browser_agent.run(last_user_msg)).get("response", "")

    elif model_requested == "arena-graphrag":
        contenu = graphrag_tool.query_global(last_user_msg).get("response", "")

    elif model_requested == "arena-rag-docs":
        contenu = lightrag_tool.query(last_user_msg, mode="hybrid")

    if contenu is not None:
        logger.info(f"Modele '{model_requested}' -> agent dedie")
        return _reponse_openai(contenu, model_requested, stream)

    # ---- arena-core : aiguillage automatique selon la question ----
    intent = await orchestrator.analyze_intent(last_user_msg)
    logger.info(f"Modele 'arena-core' -> intention detectee : {intent}")

    if intent in AGENTS_SPECIALISES:
        res = await dispatch_request(chat_req, intent=intent)
        contenu = res.get("response", "") + formater_sources(res.get("sources", []))
        return _reponse_openai(contenu, model_requested, stream)

    # ---- Discussion simple : reponse mot par mot ----
    if not stream:
        res = await dispatch_request(chat_req, intent=intent)
        return _reponse_openai(res.get("response", ""), model_requested, stream)

    async def generateur_discussion():
        cree = int(time.time())
        system_prompt = get_arena_system_prompt()

        async for jeton in fast_provider.generate_stream(last_user_msg, system_prompt):
            morceau = {
                "id": f"chatcmpl-{cree}",
                "object": "chat.completion.chunk",
                "created": cree,
                "model": model_requested,
                "choices": [{"index": 0, "delta": {"content": jeton}, "finish_reason": None}]
            }
            yield f"data: {json.dumps(morceau)}\n\n"

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

# ==============================================================================
# ENDPOINTS MÉDIAS & PIPELINES
# ==============================================================================
def valider_nom_de_fichier(nom_brut: Optional[str]) -> str:
    """Verifie le nom d'un fichier envoye et renvoie un nom sur.

    Deux controles distincts : `Path(...).name` neutralise la traversee de
    repertoire, la liste blanche d'extensions decide de ce qu'ARENA accepte.
    """
    if not nom_brut or not nom_brut.strip():
        raise HTTPException(status_code=400, detail="Nom de fichier manquant.")

    nom_sur = Path(nom_brut).name
    if not nom_sur or nom_sur in {".", ".."}:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")

    extension = Path(nom_sur).suffix.lower()
    if extension not in EXTENSIONS_MEDIA_AUTORISEES:
        autorisees = ", ".join(sorted(EXTENSIONS_MEDIA_AUTORISEES))
        # Guillemets imbriques interdits dans une f-string avant Python 3.12.
        libelle = extension or "aucune extension"
        raise HTTPException(
            status_code=415,
            detail=f"Type de fichier non autorise : '{libelle}'. "
                   f"Formats acceptes : {autorisees}."
        )
    return nom_sur


async def ecrire_par_blocs(file: UploadFile, destination: Path) -> int:
    """Ecrit le fichier bloc par bloc et renvoie sa taille.

    Depasser le plafond interrompt l'ecriture et supprime le fichier partiel :
    un envoi refuse ne doit rien laisser sur le disque.
    """
    taille = 0
    try:
        with open(destination, "wb") as tampon:
            while bloc := await file.read(TAILLE_BLOC_ENVOI):
                taille += len(bloc)
                if taille > TAILLE_MAX_ENVOI:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fichier trop volumineux (maximum "
                               f"{TAILLE_MAX_ENVOI / (1024 ** 3):.1f} Go)."
                    )
                tampon.write(bloc)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    if taille == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Fichier vide.")

    return taille


@app.post("/api/upload", dependencies=[Depends(verify_api_key)])
async def upload_video(file: UploadFile = File(...)):
    try:
        if not permissions.is_allowed("WRITE_FILES"):
            raise HTTPException(status_code=403, detail="Écriture non autorisée.")

        safe_filename = valider_nom_de_fichier(file.filename)
        incoming_dir = MEDIA_DIR / "incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)

        file_path = incoming_dir / safe_filename
        taille = await ecrire_par_blocs(file, file_path)
        logger.info(f"Fichier reçu : {safe_filename} ({taille / (1024 ** 2):.1f} Mo)")

        return {
            "status": "success",
            "filename": safe_filename,
            "path": str(file_path),
            "size_bytes": taille,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur upload: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.post("/api/process-video", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def process_video_pipeline(video_path: str = Form(...)):
    try:
        p = Path(video_path).resolve()
        try:
            p.relative_to(MEDIA_DIR.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Accès refusé.") from None

        if not p.exists():
            return {"status": "error", "message": f"Fichier introuvable: {video_path}"}

        analysis_res = await video_agent.run("Analyse complète", context={"video_path": str(p)})
        segments = analysis_res.get("segments", []) if isinstance(analysis_res, dict) else []

        clip_res = await clip_selector.run("Isole le meilleur extrait viral", context={
            "video_path": str(p),
            "segments": segments
        })

        rendered_file_path = clip_res.get("clip_path") if isinstance(clip_res, dict) else None
        if not rendered_file_path or not Path(rendered_file_path).exists():
            target_rendered = RENDERED_DIR / f"{p.stem}_vertical_9_16.mp4"
            editor_agent.crop_tool.convert_to_vertical_9_16(str(p), str(target_rendered))
            rendered_file_path = str(target_rendered)

        sub_res = await subtitle_agent.run("Génère sous-titres", context={
            "video_name": p.stem,
            "segments": segments
        })

        rendered_p = Path(rendered_file_path)
        video_web_url = f"/media/rendered/{rendered_p.name}"

        return {
            "status": "success",
            "video_original": p.name,
            "rendered_9_16": str(rendered_p),
            "video_web_url": video_web_url,
            "subtitle_srt": sub_res.get("srt_path") if isinstance(sub_res, dict) else "",
            "ai_summary": analysis_res.get("ai_analysis") if isinstance(analysis_res, dict) else ""
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur pipeline vidéo: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

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

@app.post("/api/chat", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
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

@app.post("/api/chat/stream", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
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
