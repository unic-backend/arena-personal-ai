"""Point d'entrée de l'API d'ARENA.

Ce fichier n'assemble que : l'application, sa politique d'origines, le dossier
des rendus, et les trois groupes de routes. Il faisait 652 lignes avant le
découpage — configuration, sécurité, prompts et logique métier mélangés.

    uvicorn apps.backend.main:app --host 127.0.0.1 --port 8000
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.backend.config import ALLOWED_ORIGINS, BASE_DIR, RENDERED_DIR
from apps.backend.routers import chat, media, openai_gateway
from apps.backend.runtime import deep_provider, fast_provider

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
            "FreshInfoAgent", "LightRAG", "MicrosoftGraphRAG"
        ]
    }


# L'ordre d'inclusion ne change rien au routage : les chemins ne se recouvrent pas.
app.include_router(openai_gateway.router)
app.include_router(media.router)
app.include_router(chat.router)
