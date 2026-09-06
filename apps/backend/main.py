"""Point d'entrée de l'API d'Usman.

Ce fichier n'assemble que : l'application, sa politique d'origines, le dossier
des rendus, et les trois groupes de routes. Il faisait 652 lignes avant le
découpage — configuration, sécurité, prompts et logique métier mélangés.

    uvicorn apps.backend.main:app --host 127.0.0.1 --port 8000
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.backend.config import ALLOWED_ORIGINS, BASE_DIR, OLLAMA_URL, RENDERED_DIR, docs_actives
from apps.backend.routers import (
    actions,
    chat,
    connectors,
    contexte_unifie,
    conversations,
    gardien,
    hermes_evolution,
    media,
    openai_gateway,
    pwa_gateway,
    speech,
    video_production,
)
from apps.backend.runtime import (
    agents_actifs,
    deep_provider,
    fast_provider,
    ollama_vision,
)
from apps.backend.security import cle_presentee_valide, validate_media_path, verify_media_access
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
    await verifier_modeles(
        [fast_provider.model_name, deep_provider.model_name, ollama_vision.model_name],
        OLLAMA_URL,
    )
    yield


app = FastAPI(
    title="Usman Personal AI API",
    version="1.7.0",
    lifespan=au_demarrage,
    # Fermes par defaut (VOLET « ARENA en ligne », phase 4.2) : `docs_actives()`
    # ne s'ouvre que si `.env` porte `APP_ENV=development`. FastAPI n'a aucun
    # moyen de proteger ces trois routes par une dependance — ne jamais les
    # generer est la seule fermeture qui existe.
    docs_url="/docs" if docs_actives() else None,
    redoc_url="/redoc" if docs_actives() else None,
    openapi_url="/openapi.json" if docs_actives() else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

RENDERED_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/media/rendered/{nom}", dependencies=[Depends(verify_media_access)])
async def servir_media_rendu(nom: str):
    """Sert un fichier rendu — cle en en-tete ou en parametre, jamais sans.

    Remplace le mount `StaticFiles` d'origine, qui servait n'importe quel
    fichier de ce dossier a quiconque en devinait le nom — prouve avec un
    fichier reel nomme comme `/api/upload` le nommerait (VOLET « ARENA en
    ligne », phase 4.1). `validate_media_path` refuse toute sortie de
    `media/` ; `verify_media_access` explique le parametre `cle`.
    """
    chemin = validate_media_path(str(RENDERED_DIR / nom))
    if not chemin.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return FileResponse(str(chemin))


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


# Fichiers que Vite copie de `public/` vers `dist/` sans les inliner.
# `viteSingleFile` ne touche qu'au JavaScript et au CSS ; ceux-ci restent des
# fichiers a part, et une PWA ne s'installe pas sans eux.
#
# **`sw.js` doit etre servi depuis la racine** : la portee d'un service worker
# est celle du chemin d'ou il vient. Servi depuis `/static/sw.js`, il ne
# controlerait que `/static/` — c'est-a-dire rien d'utile.
FICHIERS_PWA = ("sw.js", "manifest.webmanifest", "offline.html")


def _fichier_pwa(nom: str) -> FileResponse:
    """Rend un fichier de `dist/`, ou 404 si la PWA n'est pas compilee."""
    chemin = INTERFACE_PWA.parent / nom
    if not chemin.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"{nom} absent : la PWA n'est pas compilee (npm run build dans apps/pwa).",
        )
    return FileResponse(str(chemin))


@app.get("/sw.js")
@app.get("/manifest.webmanifest")
@app.get("/offline.html")
async def servir_fichier_pwa(request: Request):
    """Sert le service worker, le manifeste et la page hors ligne."""
    return _fichier_pwa(request.url.path.lstrip("/"))


@app.get("/icons/{nom}")
async def servir_icone_pwa(nom: str):
    """Sert une icone de la PWA, sans jamais sortir du dossier des icones.

    Le nom vient de l'URL : sans cette verification, `../../.env` serait un nom
    d'icone valide.
    """
    dossier = (INTERFACE_PWA.parent / "icons").resolve()
    chemin = (dossier / nom).resolve()
    try:
        chemin.relative_to(dossier)
    except ValueError:
        raise HTTPException(status_code=403, detail="Acces refuse.") from None
    if not chemin.is_file():
        raise HTTPException(status_code=404, detail=f"Icone {nom} introuvable.")
    return FileResponse(str(chemin))


@app.get("/ui/classique")
async def serve_frontend_classique():
    """L'ancienne interface, toujours joignable.

    Elle n'est pas supprimee : tant que la PWA n'a pas fait ses preuves, retirer
    ce qui marche pour installer ce qui est neuf n'est pas un progres.
    """
    return FileResponse(str(INTERFACE_CLASSIQUE))


@app.get("/health")
async def health_check(authorization: Optional[str] = Header(None)):
    """Etat du serveur, et **si la cle presentee ouvre vraiment quelque chose**.

    `ok` ne dit pas « le serveur est en vie » : il dit « tu peux obtenir une
    reponse maintenant ». Il faut donc les deux — le modele disponible ET une
    cle valable. Sans cela le panneau de l'interface passait au vert avec une
    mauvaise cle, et chaque message repondait 401.

    Les champs publics restent publics : cette route n'exige pas de cle, elle
    se contente de dire ce que la cle presentee vaut.
    """
    ollama_online = await fast_provider.is_available()
    authentifie = cle_presentee_valide(authorization)

    if not authentifie:
        raison = (
            "Aucune cle presentee." if not authorization
            else "La cle presentee n'est pas la bonne."
        )
    elif not ollama_online:
        raison = "Ollama est hors-ligne : demarre-le avec `ollama serve`."
    else:
        raison = ""

    return {
        # `ok`, `name`, `provider` et `model` sont lus par l'interface PWA
        # (`pingBackend`). Ils s'ajoutent aux champs existants sans en changer
        # aucun : ce que lisaient les anciens appelants est intact.
        "ok": ollama_online and authentifie,
        "authenticated": authentifie,
        "error": raison,
        "name": "ARENA",
        # **Jamais un nom ecrit en dur.** Ce champ valait « ollama » quoi qu'il
        # arrive, et l'interface l'affiche tel quel sur le telephone
        # (`backendStore.ts` : `remoteProvider: r.provider`). Un backend servi
        # par Groq annoncait donc « ollama » : un ecran qui dit « local »
        # pendant que le texte part chez un tiers.
        #
        # `fournisseur_en_service` rend `None` tant que rien n'a ete servi —
        # c'est « on ne sait pas encore », jamais « local ».
        "provider": fast_provider.fournisseur_en_service or "indetermine",
        "model": fast_provider.model_name,
        "status": "healthy" if ollama_online else "degraded",
        "ollama_available": ollama_online,
        "interface": nom_interface(),
        "models": [fast_provider.model_name, deep_provider.model_name],
        # Derivee des agents que `runtime` construit vraiment, jamais ecrite
        # a la main : la liste figee qui etait ici taisait six agents bien
        # vivants, dont l'assistant devis. Voir `runtime.agents_actifs`.
        "agents_active": agents_actifs()
    }


# L'ordre d'inclusion ne change rien au routage : les chemins ne se recouvrent pas.
app.include_router(openai_gateway.router)
app.include_router(media.router)
app.include_router(chat.router)
app.include_router(actions.router)
app.include_router(gardien.router)
app.include_router(pwa_gateway.router)
app.include_router(conversations.router)
app.include_router(connectors.router)
app.include_router(video_production.router)
app.include_router(hermes_evolution.router)
app.include_router(contexte_unifie.router)
app.include_router(speech.router)
