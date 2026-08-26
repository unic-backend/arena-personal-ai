import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from agents.browser.browser_agent import BrowserAgent
from agents.clip_selector.clip_selector_agent import ClipSelectorAgent
from agents.coder.coder_agent import CoderAgent
from agents.editor.editor_agent import EditorAgent
from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from agents.publisher.publisher_agent import PublisherAgent
from agents.repo_engineer.repo_engineer_agent import RepoEngineerAgent
from agents.researcher.researcher_agent import DeepResearcherAgent
from agents.subtitle.subtitle_agent import SubtitleAgent
from agents.swe_agent.swe_agent import SWEAgent
from agents.trend_analyzer.trend_analyzer_agent import TrendAnalyzerAgent
from agents.video_analyzer.video_analyzer_agent import VideoAnalyzerAgent
from core.memory.memory_manager import MemoryManager
from core.models.ollama_provider import OllamaProvider
from core.permissions.permission_manager import PermissionManager
from tools.rag.graphrag_tool import GraphRAGTool
from tools.rag.lightrag_tool import LightRAGTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arena.backend")

app = FastAPI(title="ARENA Personal AI API", version="1.7.0")

# Origines autorisees : les interfaces locales par defaut, surchargeables via .env
# (ARENA_ALLOWED_ORIGINS, liste separee par des virgules). Jamais "*" : le
# navigateur laisserait n'importe quel site appeler les endpoints /api.
ORIGINES_PAR_DEFAUT = "http://localhost:3000,http://localhost:3080,http://localhost:8000"
ALLOWED_ORIGINS = [
    origine.strip()
    for origine in os.getenv("ARENA_ALLOWED_ORIGINS", ORIGINES_PAR_DEFAUT).split(",")
    if origine.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

MEDIA_DIR = BASE_DIR / "media"
RENDERED_DIR = MEDIA_DIR / "rendered"

# Extensions acceptees par le studio video. C'est une regle metier, pas un
# reglage : ARENA ne traite que de l'audio et de la video.
EXTENSIONS_MEDIA_AUTORISEES = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
}

# Plafond de taille, reglable : il depend du disque de la machine.
TAILLE_MAX_ENVOI = int(os.getenv("ARENA_UPLOAD_MAX_BYTES", str(2 * 1024 * 1024 * 1024)))

# Le fichier est ecrit par blocs : `await file.read()` sans argument chargerait
# tout en memoire avant d'atteindre le disque.
TAILLE_BLOC_ENVOI = 1024 * 1024
RENDERED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/rendered", StaticFiles(directory=str(RENDERED_DIR)), name="rendered")

DB_PATH = BASE_DIR / "data" / "database" / "memory.db"
memory = MemoryManager(db_path=str(DB_PATH))
permissions = PermissionManager()
lightrag_tool = LightRAGTool()
graphrag_tool = GraphRAGTool()

# Configuration lue depuis le fichier .env (valeurs de secours si absent)
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MODELE_RAPIDE = os.getenv("CODER_LOCAL_MODEL", "qwen2.5-coder:14b")
MODELE_PROFOND = os.getenv("DEFAULT_LOCAL_MODEL", "qwen3.5:9b")

fast_provider = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_RAPIDE)
deep_provider = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_PROFOND)

# Équipe complète de 12 Agents d'Élite
orchestrator = OrchestratorAgent(provider=fast_provider, memory=memory)
trend_agent = TrendAnalyzerAgent(provider=deep_provider, memory=memory)
video_agent = VideoAnalyzerAgent(provider=deep_provider, memory=memory)
editor_agent = EditorAgent(provider=deep_provider, memory=memory)
subtitle_agent = SubtitleAgent(provider=deep_provider, memory=memory)
coder_agent = CoderAgent(provider=fast_provider, memory=memory)
researcher_agent = DeepResearcherAgent(provider=deep_provider, memory=memory)
clip_selector = ClipSelectorAgent(provider=deep_provider, memory=memory)
publisher_agent = PublisherAgent(provider=fast_provider, memory=memory)
browser_agent = BrowserAgent(provider=fast_provider, memory=memory)
repo_engineer = RepoEngineerAgent(provider=fast_provider, memory=memory)
swe_agent = SWEAgent(provider=fast_provider, memory=memory)

memory.set_fact("user_profile", "owner", "Saer", {"role": "Propriétaire et créateur d'ARENA"})

def get_arena_system_prompt() -> str:
    owner_name = memory.get_fact("owner") or "Saer"
    president_fact = memory.get_fact("president") or "Bassirou Diomaye Faye (depuis avril 2024)"
    pm_fact = memory.get_fact("premier_ministre") or "Ousmane Sonko (depuis avril 2024)"
    return (
        f"Tu es ARENA, l'IA autonome personnelle de {owner_name}.\n"
        f"FAITS OFFICIELS DU SÉNÉGAL :\n"
        f"- Le Président de la République du Sénégal est : {president_fact}.\n"
        f"- Le Premier ministre du Sénégal est : {pm_fact}.\n"
        f"- Année actuelle : 2026.\n"
        f"Ton propriétaire s'appelle {owner_name}. Réponds en français de manière exacte, claire et directe."
    )

# ==============================================================================
# SECURITE : cle API partagee (/v1 et /api) + validation des chemins media
# ==============================================================================
ARENA_API_KEY = os.getenv("ARENA_API_KEY", "")

def verify_api_key(authorization: Optional[str] = Header(None)):
    """Bloque tout appel a /v1 ou /api qui ne presente pas la bonne cle Bearer."""
    if not ARENA_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ARENA_API_KEY absente du fichier .env : passerelle desactivee par securite."
        )
    if authorization != f"Bearer {ARENA_API_KEY}":
        raise HTTPException(status_code=401, detail="Cle API invalide ou manquante.")
    return True


def validate_media_path(raw_path: str) -> Path:
    """Garantit qu'un chemin de fichier reste a l'interieur du dossier media/."""
    p = Path(raw_path).resolve()
    try:
        p.relative_to(MEDIA_DIR.resolve())
    except ValueError:
        # `from None` : l'erreur interne de chemin n'a pas a remonter au client.
        raise HTTPException(
            status_code=403,
            detail="Acces refuse : le fichier doit se trouver dans le dossier media/."
        ) from None
    return p


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


@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
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

    if intent in ["DEEP_REASONING", "DEEP_RESEARCH", "TREND_SEARCH", "CODE_EXECUTION", "VIDEO_ANALYSIS"]:
        res = await dispatch_request(chat_req)
        return _reponse_openai(res.get("response", ""), model_requested, stream)

    # ---- Discussion simple : reponse mot par mot ----
    if not stream:
        res = await dispatch_request(chat_req)
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

@app.post("/api/process-video", dependencies=[Depends(verify_api_key)])
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

    memory.add_chat_message(session_id=session_id, role="user", content=request.prompt)
    memory.add_chat_message(session_id=session_id, role="assistant", content=result["response"])
    return result

@app.post("/api/chat", dependencies=[Depends(verify_api_key)])
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
            "response": result["response"]
        }
    except Exception as e:
        logger.error(f"Erreur endpoint chat: {e}", exc_info=True)
        return {"status": "error", "model": "error", "response": f"❌ {str(e)}"}

@app.post("/api/chat/stream", dependencies=[Depends(verify_api_key)])
async def chat_stream_endpoint(request: ChatRequest):
    session_id = request.session_id or "default"
    intent = await orchestrator.analyze_intent(request.prompt)

    if intent in ["DEEP_REASONING", "DEEP_RESEARCH", "TREND_SEARCH", "CODE_EXECUTION", "VIDEO_ANALYSIS"]:
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
