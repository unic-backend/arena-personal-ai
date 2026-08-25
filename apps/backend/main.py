import os
import sys
import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from core.permissions.permission_manager import PermissionManager

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from agents.trend_analyzer.trend_analyzer_agent import TrendAnalyzerAgent
from agents.video_analyzer.video_analyzer_agent import VideoAnalyzerAgent
from agents.editor.editor_agent import EditorAgent
from agents.subtitle.subtitle_agent import SubtitleAgent
from agents.coder.coder_agent import CoderAgent
from agents.researcher.researcher_agent import DeepResearcherAgent
from agents.clip_selector.clip_selector_agent import ClipSelectorAgent
from agents.publisher.publisher_agent import PublisherAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arena.backend")

app = FastAPI(title="ARENA Personal AI API", version="0.9.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RENDERED_DIR = BASE_DIR / "media" / "rendered"
RENDERED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/rendered", StaticFiles(directory=str(RENDERED_DIR)), name="rendered")

DB_PATH = BASE_DIR / "data" / "database" / "memory.db"
memory = MemoryManager(db_path=str(DB_PATH))
permissions = PermissionManager()

fast_provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen2.5-coder:14b")
deep_provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")

orchestrator = OrchestratorAgent(provider=fast_provider, memory=memory)
trend_agent = TrendAnalyzerAgent(provider=deep_provider, memory=memory)
video_agent = VideoAnalyzerAgent(provider=deep_provider, memory=memory)
editor_agent = EditorAgent(provider=deep_provider, memory=memory)
subtitle_agent = SubtitleAgent(provider=deep_provider, memory=memory)
coder_agent = CoderAgent(provider=fast_provider, memory=memory)
researcher_agent = DeepResearcherAgent(provider=deep_provider, memory=memory)
clip_selector = ClipSelectorAgent(provider=deep_provider, memory=memory)
publisher_agent = PublisherAgent(provider=fast_provider, memory=memory)

memory.set_fact("user_profile", "owner", "Saer", {"role": "Propriétaire et créateur d'ARENA"})

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
            "Orchestrator", "ReasoningEngine", "CoderAgent", "DeepResearcher",
            "TrendAnalyzer", "VideoAnalyzer", "Editor", "Subtitle", "ClipSelector", "Publisher"
        ]
    }

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    try:
        incoming_dir = BASE_DIR / "media" / "incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = incoming_dir / file.filename
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
            
        return {
            "status": "success",
            "filename": file.filename,
            "path": str(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-video")
async def process_video_pipeline(video_path: str = Form(...)):
    try:
        p = Path(video_path)
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
    except Exception as e:
        logger.error(f"Erreur pipeline vidéo: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    session_id = request.session_id or "default"
    owner_name = memory.get_fact("owner") or "Saer"
    
    intent = await orchestrator.analyze_intent(request.prompt)
    logger.info(f"Intention détectée pour streaming: {intent}")

    if intent == "DEEP_REASONING":
        result = await orchestrator.run(request.prompt, context={"session_id": session_id})
        async def reasoning_gen():
            yield f"data: {json.dumps({'token': result['response'], 'intent': intent})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(reasoning_gen(), media_type="text/event-stream")

    elif intent == "DEEP_RESEARCH":
        result = await researcher_agent.run(request.prompt)
        async def text_gen():
            yield f"data: {json.dumps({'token': result['response'], 'intent': intent})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(text_gen(), media_type="text/event-stream")

    elif intent == "TREND_SEARCH":
        result = await trend_agent.run(request.prompt, context={"region": request.region})
        async def trend_gen():
            yield f"data: {json.dumps({'token': result['response'], 'intent': intent})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(trend_gen(), media_type="text/event-stream")

    elif intent == "CODE_EXECUTION":
        result = await coder_agent.run(request.prompt)
        async def code_gen():
            yield f"data: {json.dumps({'token': result['response'], 'intent': intent})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(code_gen(), media_type="text/event-stream")

    else:
        history = memory.get_recent_history(session_id=session_id, limit=6)
        memory.add_chat_message(session_id=session_id, role="user", content=request.prompt)

        system_prompt = f"Tu es ARENA, l'IA autonome personnelle de {owner_name}. Ton propriétaire s'appelle {owner_name}. Réponds directement et poliment en français."
        
        prompt_lines = []
        for msg in history:
            role_label = owner_name if msg["role"] == "user" else "ARENA"
            prompt_lines.append(f"{role_label}: {msg['content']}")
        prompt_lines.append(f"{owner_name}: {request.prompt}")
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