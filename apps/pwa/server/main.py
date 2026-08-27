"""Usman AI backend: real model streaming + observable activity events.

Run:
    cp .env.example .env
    # fill provider/model/key in .env
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8787
"""

from __future__ import annotations

import hmac
import json
import os
import time
import uuid
import asyncio
from contextlib import asynccontextmanager, suppress
from collections import deque
from dataclasses import dataclass, field

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from providers import ProviderError, load_config, probe_provider, stream_model
from attachments import (
    MAX_FILE_BYTES,
    AttachmentError,
    get_attachments,
    purge_expired,
    store_attachment,
)
from oauth import (
    start_oauth_flow,
    handle_oauth_callback,
    get_connector_session,
    disconnect_connector_session,
    verify_api_token,
)

load_dotenv()


async def cleanup_attachments():
    while True:
        await asyncio.sleep(300)
        purge_expired()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    cleanup_task = asyncio.create_task(cleanup_attachments())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(title="Usman AI backend", version="1.0.0", lifespan=lifespan)

default_origins = "http://localhost:5173,http://127.0.0.1:5173"
allowed_origins = [
    origin.strip()
    for origin in os.getenv("USMAN_ALLOWED_ORIGINS", default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Last-Event-ID", "X-Usman-Run-ID"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    return response


# ── auth ─────────────────────────────────────────────────────

def require_backend_auth(request: Request) -> None:
    """Protect the Usman API when USMAN_BACKEND_TOKEN is configured."""
    expected = os.getenv("USMAN_BACKEND_TOKEN", "").strip()
    if not expected:
        return
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid backend access token")


# ── activity-event helpers ───────────────────────────────────

def now_ms() -> int:
    return int(time.time() * 1000)


def event(kind: str, title: str, **fields) -> dict:
    return {
        "id": f"ev_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "title": title,
        "status": fields.pop("status", "running"),
        "phase": fields.pop("phase", "started"),
        "startedAt": now_ms(),
        **fields,
    }


def patch(event_value: dict, **fields) -> dict:
    """Return the updated event; the frontend upserts it by its stable id."""
    updated = {**event_value, **fields}
    if updated["status"] in {"completed", "failed", "cancelled"}:
        updated["completedAt"] = now_ms()
        updated["durationMs"] = updated["completedAt"] - updated["startedAt"]
    return updated


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── Resumable SSE streams ─────────────────────────────────────

@dataclass
class RunStream:
    run_id: str
    frames: deque[tuple[int, dict]] = field(default_factory=lambda: deque(maxlen=2000))
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    done: bool = False
    created_at: float = field(default_factory=time.time)
    next_id: int = 1
    task: asyncio.Task | None = None

    async def emit(self, payload: dict) -> None:
        event_id = self.next_id
        self.next_id += 1
        self.frames.append((event_id, payload))
        for queue in tuple(self.subscribers):
            await queue.put((event_id, payload))
        if payload.get("type") in {"done", "error"}:
            self.done = True

    def format_frame(self, event_id: int, payload: dict) -> str:
        return f"id: {event_id}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


RUN_STREAMS: dict[str, RunStream] = {}


def purge_run_streams() -> None:
    cutoff = time.time() - 900
    for run_id, stream in list(RUN_STREAMS.items()):
        if stream.done and stream.created_at < cutoff:
            RUN_STREAMS.pop(run_id, None)


async def execute_agent_run(
    stream: RunStream,
    *,
    text: str,
    history: list,
    locale: str,
    attachments: list,
    persona: dict | None = None,
    memories: list | None = None,
) -> None:
    cfg = load_config()
    fr = locale == "fr"
    persona = persona or {}
    persona_instructions = persona.get("instructions") or ""
    memories = memories or []

    user_name = persona.get("user_name")
    desc_suffix = f" · Utilisateur: {user_name}" if (user_name and fr) else f" · User: {user_name}" if user_name else ""

    preparation = event(
        "analysis",
        "Préparation du contexte" if fr else "Preparing context",
        tool="request_context",
        description=(
            f"{min(len(history), 16)} messages précédents · {len(attachments)} pièce(s) jointe(s){desc_suffix}"
            if fr
            else f"{min(len(history), 16)} previous messages · {len(attachments)} attachment(s){desc_suffix}"
        ),
    )
    await stream.emit({"type": "activity", "event": preparation})
    preparation = patch(
        preparation,
        status="completed",
        phase="completed",
        output={
            "history_messages": min(len(history), 16),
            "locale": locale,
            "attachments": [value.public() for value in attachments],
            "persona": bool(persona_instructions),
            "memories_count": len(memories),
        },
    )
    await stream.emit({"type": "activity", "event": preparation})

    # If active long-term memories exist, emit an observable memory recall event
    if memories:
        mem_event = event(
            "database",
            "Consultation de la mémoire" if fr else "Recalling personal memory",
            tool="memory_vault",
            description=(
                f"{len(memories)} fait(s) mémorisé(s) pris en compte"
                if fr
                else f"{len(memories)} active personal memory item(s)"
            ),
            output={"count": len(memories), "items": [m.get("content", "")[:60] for m in memories[:4]]},
        )
        await stream.emit({"type": "activity", "event": mem_event})
        mem_event = patch(mem_event, status="completed", phase="completed")
        await stream.emit({"type": "activity", "event": mem_event})

    # Format memories into prompt instructions
    memory_prompt = ""
    if memories:
        mem_lines = ["\n[Usman Active Long-Term Memories]"]
        for m in memories:
            cat = m.get("category", "fact").upper()
            content = m.get("content", "").strip()
            if content:
                mem_lines.append(f"- [{cat}] {content}")
        memory_prompt = "\n".join(mem_lines)

    combined_instructions = f"{persona_instructions}\n{memory_prompt}".strip()

    model_call = event(
        "tool",
        "Interrogation du modèle" if fr else "Calling AI model",
        tool=f"model_{cfg.provider or 'unconfigured'}",
        description=(
            f"{cfg.label} · {cfg.model or 'modèle non configuré'}"
            if fr
            else f"{cfg.label} · {cfg.model or 'model not configured'}"
        ),
        input={"provider": cfg.provider, "model": cfg.model},
    )
    await stream.emit({"type": "activity", "event": model_call})

    chunks = 0
    characters = 0
    first_token_at = None
    try:
        async for delta in stream_model(
            cfg,
            text,
            history,
            attachments,
            persona_instructions=combined_instructions,
        ):
            if not delta:
                continue
            chunks += 1
            characters += len(delta)
            if first_token_at is None:
                first_token_at = now_ms()
                model_call = patch(
                    model_call,
                    phase="progress",
                    status="running",
                    description=(
                        f"Réponse diffusée depuis {cfg.label}…"
                        if fr
                        else f"Streaming response from {cfg.label}…"
                    ),
                    metadata={"firstTokenMs": first_token_at - model_call["startedAt"]},
                )
                await stream.emit({"type": "activity", "event": model_call})
            await stream.emit({"type": "token", "text": delta})

        if chunks == 0:
            raise ProviderError("The provider completed without returning text")
        model_call = patch(
            model_call,
            status="completed",
            phase="completed",
            description=(
                f"Réponse terminée · {chunks} fragments"
                if fr
                else f"Response completed · {chunks} chunks"
            ),
            output={
                "provider": cfg.provider,
                "model": cfg.model,
                "chunks": chunks,
                "characters": characters,
                "firstTokenMs": first_token_at - model_call["startedAt"] if first_token_at else None,
            },
        )
        await stream.emit({"type": "activity", "event": model_call})
        await stream.emit({"type": "done", "meta": {"provider": cfg.provider, "model": cfg.model}})
    except Exception as exc:
        safe_error = str(exc)[:500]
        model_call = patch(
            model_call,
            status="failed",
            phase="failed",
            title="Échec du modèle IA" if fr else "AI model failed",
            description=safe_error,
            output={"provider": cfg.provider, "model": cfg.model},
        )
        await stream.emit({"type": "activity", "event": model_call})
        await stream.emit({"type": "error", "message": safe_error})


# ── health: verifies the actual provider without generating tokens ──

@app.get("/health")
async def health(request: Request):
    require_backend_auth(request)
    cfg = load_config()
    ok, error = await probe_provider(cfg)
    return {
        "ok": ok,
        "name": "Usman",
        "provider": cfg.label if cfg.provider else None,
        "model": cfg.model or None,
        "configured": cfg.configured,
        "error": error,
    }


# ── main model stream ─────────────────────────────────────────

@app.post("/files")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form(""),
):
    """Receive, validate and inspect one temporary attachment."""
    require_backend_auth(request)
    data = await file.read(MAX_FILE_BYTES + 1)
    try:
        stored = store_attachment(
            file.filename or "attachment",
            file.content_type or "application/octet-stream",
            kind,
            data,
        )
    except AttachmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()
    return stored.public()

@app.post("/agent/stream")
async def agent_stream(request: Request):
    require_backend_auth(request)
    body = await request.json()
    text = str(body.get("text", "")).strip()
    history = body.get("history", [])
    attachment_ids = body.get("attachments", [])
    locale = str(body.get("locale", "en"))
    persona = body.get("persona")
    memories = body.get("memories") or []
    if not text:
        raise HTTPException(status_code=422, detail="A non-empty text prompt is required")
    if not isinstance(history, list):
        history = []
    if not isinstance(attachment_ids, list):
        raise HTTPException(status_code=422, detail="attachments must be an array")
    try:
        attachments = get_attachments([str(value) for value in attachment_ids])
    except AttachmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    purge_run_streams()
    run_id = str(body.get("run_id") or request.headers.get("x-usman-run-id") or uuid.uuid4())
    last_event_raw = request.headers.get("last-event-id", "0")
    try:
        last_event_id = max(0, int(last_event_raw))
    except ValueError:
        last_event_id = 0

    stream = RUN_STREAMS.get(run_id)
    if stream is None:
        stream = RunStream(run_id=run_id)
        RUN_STREAMS[run_id] = stream
        stream.task = asyncio.create_task(
            execute_agent_run(
                stream,
                text=text,
                history=history,
                locale=locale,
                attachments=attachments,
                persona=persona,
                memories=memories,
            )
        )

    async def generate():
        # Replay only events the client has not acknowledged.
        for event_id, payload in tuple(stream.frames):
            if event_id > last_event_id:
                yield stream.format_frame(event_id, payload)

        if stream.done:
            return

        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        stream.subscribers.add(queue)
        try:
            while True:
                try:
                    event_id, payload = await asyncio.wait_for(queue.get(), timeout=15)
                    if event_id > last_event_id:
                        yield stream.format_frame(event_id, payload)
                    if payload.get("type") in {"done", "error"}:
                        return
                except asyncio.TimeoutError:
                    # Standards-compliant SSE comment heartbeat; ignored by the UI parser.
                    yield ": keep-alive\n\n"
                if await request.is_disconnected():
                    return
        finally:
            stream.subscribers.discard(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Real OAuth 2.0 & Connector Routes ─────────────────────────

@app.get("/connectors/{connector_id}/auth")
async def connector_auth(connector_id: str, request: Request, key: str = "anon"):
    return await start_oauth_flow(connector_id, request, key=key)


@app.get("/connectors/{connector_id}/callback")
async def connector_callback(connector_id: str, request: Request):
    return await handle_oauth_callback(connector_id, request)


@app.get("/connectors/{connector_id}/status")
def connector_status(connector_id: str, request: Request):
    require_backend_auth(request)
    auth_key = request.headers.get("authorization", "").removeprefix("Bearer ").strip() or "anon"
    session = get_connector_session(connector_id, auth_key)
    return {
        "connected": session is not None,
        "account": session["account"] if session else None,
        "verified": session.get("verified", False) if session else False,
    }


@app.post("/connectors/{connector_id}/disconnect")
def connector_disconnect(connector_id: str, request: Request):
    require_backend_auth(request)
    auth_key = request.headers.get("authorization", "").removeprefix("Bearer ").strip() or "anon"
    ok = disconnect_connector_session(connector_id, auth_key)
    return {"ok": ok}


@app.post("/connectors/verify")
async def connector_verify(request: Request):
    require_backend_auth(request)
    body = await request.json()
    token = str(body.get("token", "")).strip()
    cid = str(body.get("id", "")).strip()
    ok, account = await verify_api_token(cid, token)
    return {"ok": ok, "account": account}