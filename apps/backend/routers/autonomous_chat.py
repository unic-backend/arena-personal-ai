"""POST /api/v1/chat : meme cle proprietaire, nouvelle orchestration native."""
import asyncio
from contextlib import suppress
from functools import lru_cache

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from apps.backend.security import limiter_debit, verify_api_key
from apps.backend.services.ai_client import AIClient
from apps.backend.services.memory_engine import MemoryEngine
from apps.backend.services.orchestrator import ChatInput, ChatOutput, CurrentUser, Orchestrator
from apps.backend.services.settings import AutonomousSettings
from apps.backend.services.tools.builtin import builtin_registry
from core.memory.personnelle import MemoirePersonnelle
from core.models.usage import CompteurUsage

router = APIRouter()


def current_user(authenticated: bool = Depends(verify_api_key)) -> CurrentUser:
    """La cle existante identifie l'unique proprietaire, pas un user_id du corps JSON."""
    if authenticated is not True:
        raise HTTPException(status_code=401, detail="Authentification requise.")
    return CurrentUser(id="owner")


class AutonomousRuntime:
    def __init__(self, settings: AutonomousSettings, usage: CompteurUsage | None = None,
                 legacy_memory: MemoirePersonnelle | None = None,
                 pieces_jointes=None, vision_agent=None, video_agent=None, registre=None):
        self.ai = AIClient(settings, usage=usage)
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2), follow_redirects=False)
        self.memory = MemoryEngine(settings, self.ai, legacy_memory=legacy_memory)
        self.orchestrator = Orchestrator(
            settings, self.ai, self.memory,
            builtin_registry(
                self.http, settings.tavily_key,
                pieces_jointes=pieces_jointes,
                vision_agent=vision_agent,
                video_agent=video_agent,
                registre=registre,
            ),
        )
        self.worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self.worker is None:
            self.worker = asyncio.create_task(self.memory.worker(), name="arena-memory-consolidation")

    async def close(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker
            self.worker = None
        await self.ai.close()
        await self.http.aclose()


@lru_cache(maxsize=1)
def get_runtime() -> AutonomousRuntime:
    from apps.backend.runtime import (
        compteur_usage,
        memoire_personnelle,
        pieces_jointes,
        registre,
        video_agent,
        vision_agent,
    )

    return AutonomousRuntime(
        AutonomousSettings.from_env(),
        usage=compteur_usage,
        legacy_memory=memoire_personnelle,
        pieces_jointes=pieces_jointes,
        vision_agent=vision_agent,
        video_agent=video_agent,
        registre=registre,
    )


@router.post("/api/v1/chat", response_model=ChatOutput,
             dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def autonomous_chat(request: ChatInput, background_tasks: BackgroundTasks,
                          user: CurrentUser = Depends(current_user),
                          runtime: AutonomousRuntime = Depends(get_runtime)) -> ChatOutput:
    result = await runtime.orchestrator.run(user, request)
    if result.memory_saved:
        background_tasks.add_task(runtime.memory.drain)
    return result
