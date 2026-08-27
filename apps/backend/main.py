"""Point d'entrée de l'API d'Usman.

Ce fichier n'assemble que : l'application, sa politique d'origines, le dossier
des rendus, et les trois groupes de routes. Il faisait 652 lignes avant le
découpage — configuration, sécurité, prompts et logique métier mélangés.

    uvicorn apps.backend.main:app --host 127.0.0.1 --port 8000
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.backend.config import ALLOWED_ORIGINS, BASE_DIR, OLLAMA_URL, RENDERED_DIR
from apps.backend.routers import actions, chat, media, openai_gateway
from apps.backend.runtime import deep_provider, fast_provider
from apps.backend.verification_modeles import verifier_modeles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("usman.backend")

@asynccontextmanager
async def au_demarrage(_: FastAPI):
    """Dit au demarrage si les modeles declares sont installes.

    Le controle ne bloque jamais : il journalise. Un serveur qui refuse de
    demarrer parce qu'un modele manque est moins utile qu'un serveur qui
    demarre en disant lequel manque.

    `lifespan` plutot que `on_event` : ce dernier est deprecie par FastAPI et
    laissait un avertissement a chaque execution de la suite.
    """
    await verifier_modeles([fast_provider.model_name, deep_provider.model_name], OLLAMA_URL)
    yield


app = FastAPI(title="Usman Personal AI API", version="1.7.0", lifespan=au_demarrage)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

RENDERED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/rendered", StaticFiles(directory=str(RENDERED_DIR)), name="rendered")

# Fichiers tiers embarques (Tailwind) : l'interface doit s'afficher sans Internet.
# Origine et empreinte : apps/frontend/vendor/PROVENANCE.md
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "apps" / "frontend" / "vendor")),
    name="static",
)


# --- Interface ----------------------------------------------------------------
# Deux interfaces existent, et l'une remplace l'autre sans l'effacer.
#
# `apps/pwa/` est l'application React du proprietaire. Compilee par Vite avec
# `vite-plugin-singlefile`, elle tient dans **un seul fichier** ou tout est
# inline : aucun asset a monter, aucun chemin a faire correspondre.
#
# Mais `dist/` est ignore par Git — un depot fraichement clone ne la contient
# pas. Servir un chemin qui n'existe pas rendrait une page blanche sans dire
# pourquoi. Le serveur regarde donc si elle est compilee, et le dit dans
# `/health` : « pwa » ou « classique ». Une interface manquante est un etat, pas
# une panne silencieuse.

INTERFACE_PWA = BASE_DIR / "apps" / "pwa" / "dist" / "index.html"
INTERFACE_CLASSIQUE = BASE_DIR / "apps" / "frontend" / "index.html"


def interface_servie() -> Path:
    """Le fichier reellement rendu sur `/`.

    La PWA gagne des qu'elle est compilee. Sinon l'ancienne interface repond,
    pour qu'`ARENA` reste utilisable pendant que la nouvelle est en travaux.
    """
    return INTERFACE_PWA if INTERFACE_PWA.exists() else INTERFACE_CLASSIQUE


def nom_interface() -> str:
    """« pwa » ou « classique », pour que /health le dise sans deviner."""
    return "pwa" if INTERFACE_PWA.exists() else "classique"


@app.get("/")
async def serve_frontend():
    """L'interface d'ARENA. La PWA compilee, ou l'ancienne a defaut."""
    return FileResponse(str(interface_servie()))


@app.get("/ui/classique")
async def serve_frontend_classique():
    """L'ancienne interface, toujours joignable.

    Elle n'est pas supprimee : tant que la PWA n'a pas fait ses preuves, retirer
    ce qui marche pour installer ce qui est neuf n'est pas un progres.
    """
    return FileResponse(str(INTERFACE_CLASSIQUE))


@app.get("/health")
async def health_check():
    ollama_online = await fast_provider.is_available()
    return {
        "status": "healthy" if ollama_online else "degraded",
        "ollama_available": ollama_online,
        "interface": nom_interface(),
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
app.include_router(actions.router)
