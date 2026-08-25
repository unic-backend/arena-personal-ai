import os
import sys
import logging
import traceback
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

app = FastAPI(title="ARENA Personal AI API", version="0.7.1")

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

default_provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen3.5:9b")
coder_provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen2.5-coder:14b")

# Équipe complète de 9 Agents
orchestrator = OrchestratorAgent(provider=default_provider, memory=memory)
trend_agent = TrendAnalyzerAgent(provider=default_provider, memory=memory)
video_agent = VideoAnalyzerAgent(provider=default_provider, memory=memory)
editor_agent = EditorAgent(provider=default_provider, memory=memory)
subtitle_agent = SubtitleAgent(provider=default_provider, memory=memory)
coder_agent = CoderAgent(provider=coder_provider, memory=memory)
researcher_agent = DeepResearcherAgent(provider=default_provider, memory=memory)
clip_selector = ClipSelectorAgent(provider=default_provider, memory=memory)
publisher_agent = PublisherAgent(provider=default_provider, memory=memory)

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
    ollama_online = await default_provider.is_available()
    return {
        "status": "healthy" if ollama_online else "degraded",
        "ollama_available": ollama_online,
        "models": [default_provider.model_name, coder_provider.model_name],
        "agents_active": [
            "Orchestrator", "CoderAgent", "DeepResearcher", "TrendAnalyzer",
            "VideoAnalyzer", "Editor", "Subtitle", "ClipSelector", "Publisher"
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

        # 1. Analyse & Transcription complète
        analysis_res = await video_agent.run("Analyse complète", context={"video_path": str(p)})
        segments = analysis_res.get("segments", []) if isinstance(analysis_res, dict) else []

        # 2. Détection du meilleur moment viral & Découpe 9:16 par ClipSelectorAgent
        clip_res = await clip_selector.run("Isole le meilleur extrait viral", context={
            "video_path": str(p),
            "segments": segments
        })

        rendered_file_path = clip_res.get("clip_path") if isinstance(clip_res, dict) else None
        if not rendered_file_path or not Path(rendered_file_path).exists():
            target_rendered = RENDERED_DIR / f"{p.stem}_vertical_9_16.mp4"
            editor_agent.crop_tool.convert_to_vertical_9_16(str(p), str(target_rendered))
            rendered_file_path = str(target_rendered)

        # 3. Sous-titres
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

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        session_id = request.session_id or "default"
        
        if not await default_provider.is_available():
            return {
                "status": "error",
                "model": default_provider.model_name,
                "response": "❌ Ollama est hors-ligne sur http://127.0.0.1:11434"
            }

        intent = await orchestrator.analyze_intent(request.prompt)
        logger.info(f"Intention détectée par ARENA: {intent}")

        if intent == "DEEP_RESEARCH":
            result = await researcher_agent.run(request.prompt)
        elif intent == "CODE_EXECUTION":
            result = await coder_agent.run(request.prompt)
        elif intent == "TREND_SEARCH":
            result = await trend_agent.run(request.prompt, context={"region": request.region})
        elif intent == "VIDEO_ANALYSIS" and request.video_path:
            result = await video_agent.run(request.prompt, context={"video_path": request.video_path})
        elif "PUBLI" in request.prompt.upper() or "POSTER" in request.prompt.upper():
            result = await publisher_agent.run(request.prompt, context={"video_path": request.video_path})
        else:
            result = await orchestrator.run(user_input=request.prompt, context={"session_id": session_id})

        memory.add_chat_message(session_id=session_id, role="user", content=request.prompt)
        memory.add_chat_message(session_id=session_id, role="assistant", content=result["response"])

        return {
            "status": "success",
            "model": coder_provider.model_name if intent == "CODE_EXECUTION" else default_provider.model_name,
            "intent": intent,
            "agent": result.get("agent", "OrchestratorAgent"),
            "response": result["response"]
        }

    except Exception as e:
        err_msg = f"Erreur Python ({type(e).__name__}): {str(e)}"
        logger.error(err_msg, exc_info=True)
        return {
            "status": "error",
            "model": "error",
            "response": f"❌ {err_msg}"
        }