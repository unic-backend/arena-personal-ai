"""ARENA video toolbox and optional Agnes provider integration."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from apps.backend.config import RENDERED_DIR
from tools.video.ffmpeg_tool import FFmpegTool


class AgnesError(RuntimeError):
    """Raised when the configured Agnes service cannot satisfy a request."""


@dataclass(frozen=True)
class AgnesTask:
    task_id: str
    status: str
    payload: dict[str, Any]


class AgnesVideoProvider:
    """Stdlib-only adapter for a separately self-hosted Agnes service."""

    name = "agnes"

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.getenv("AGNES_VIDEO_URL", "http://127.0.0.1:8765")).rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, *, fields: dict[str, Any] | None = None) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if fields is not None:
            encoded = {
                key: json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)
                for key, value in fields.items()
                if value is not None
            }
            data = urllib.parse.urlencode(encoded).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AgnesError(f"Agnes unavailable: {exc}") from exc
        if "json" in content_type:
            return json.loads(raw.decode("utf-8"))
        return raw

    def health(self) -> dict[str, Any]:
        try:
            return {"available": True, "provider": self.name, "config": self._request("GET", "/api/config")}
        except AgnesError as exc:
            return {"available": False, "provider": self.name, "reason": str(exc)}

    def models(self) -> Any:
        return self._request("GET", "/api/models")

    def voices(self) -> Any:
        return self._request("GET", "/api/voices")

    def create_simple(self, prompt: str, *, mode: str = "t2v", duration: int = 5, resolution: str = "768x1152") -> AgnesTask:
        return self._task(self._request("POST", "/api/tasks/simple", fields={
            "prompt": prompt, "mode": mode, "duration": duration, "resolution": resolution,
        }))

    def create_creative(self, **fields: Any) -> AgnesTask:
        return self._task(self._request("POST", "/api/tasks/creative", fields=fields))

    def create_manuscript(self, manuscript_text: str, **fields: Any) -> AgnesTask:
        return self._task(self._request("POST", "/api/tasks/manuscript", fields={"manuscript_text": manuscript_text, **fields}))

    def create_poetry(self, **fields: Any) -> AgnesTask:
        return self._task(self._request("POST", "/api/tasks/poetry", fields=fields))

    def create_anchor(self, **fields: Any) -> AgnesTask:
        return self._task(self._request("POST", "/api/tasks/anchor", fields=fields))

    def task(self, task_id: str) -> AgnesTask:
        return self._task(self._request("GET", f"/api/tasks/{self._id(task_id)}"))

    def stop(self, task_id: str) -> Any:
        return self._request("POST", f"/api/tasks/{self._id(task_id)}/stop", fields={})

    def resume(self, task_id: str) -> Any:
        return self._request("POST", f"/api/tasks/{self._id(task_id)}/resume", fields={})

    def artifacts(self, task_id: str) -> Any:
        return self._request("GET", f"/api/tasks/{self._id(task_id)}/artifacts")

    def download_video(self, task_id: str, destination: str | Path) -> Path:
        raw = self._request("GET", f"/api/video/{self._id(task_id)}")
        if not isinstance(raw, bytes):
            raise AgnesError("Agnes returned metadata instead of video bytes")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return target

    @staticmethod
    def _id(task_id: str) -> str:
        value = str(task_id).strip()
        if not value or "/" in value or "\\" in value or ".." in value:
            raise ValueError("invalid Agnes task id")
        return urllib.parse.quote(value, safe="")

    @staticmethod
    def _task(payload: Any) -> AgnesTask:
        if not isinstance(payload, dict):
            raise AgnesError("invalid Agnes task response")
        task_id = payload.get("task_id") or payload.get("id")
        if not task_id:
            raise AgnesError("Agnes response does not contain a task id")
        return AgnesTask(str(task_id), str(payload.get("status", "created")), payload)


@dataclass(frozen=True)
class VideoWorkflowResult:
    provider: str
    task: AgnesTask
    output: Path | None = None
    postprocess: dict[str, Any] | None = None


class ArenaVideoOrchestrator:
    """Use Agnes alone or compose its final artifact with ARENA tooling."""

    def __init__(self, agnes: AgnesVideoProvider | None = None):
        self.agnes = agnes or AgnesVideoProvider()

    def generate(self, prompt: str, *, workflow: str = "simple", **options: Any) -> AgnesTask:
        if workflow == "simple":
            return self.agnes.create_simple(prompt, **options)
        if workflow == "creative":
            return self.agnes.create_creative(prompt=prompt, **options)
        if workflow == "manuscript":
            return self.agnes.create_manuscript(prompt, **options)
        if workflow == "poetry":
            return self.agnes.create_poetry(prompt=prompt, **options)
        if workflow == "anchor":
            return self.agnes.create_anchor(prompt=prompt, **options)
        raise ValueError(f"unsupported video workflow: {workflow}")

    def collect(self, task_id: str, destination: str | Path, *, postprocessor: Callable[[Path], dict[str, Any] | None] | None = None) -> VideoWorkflowResult:
        task = self.agnes.task(task_id)
        if task.status.lower() not in {"completed", "complete", "success", "succeeded"}:
            return VideoWorkflowResult(provider=self.agnes.name, task=task)
        output = self.agnes.download_video(task_id, destination)
        postprocess = postprocessor(output) if postprocessor else None
        return VideoWorkflowResult(self.agnes.name, task, output, postprocess)


_SUCCESS = {"completed", "complete", "success", "succeeded"}


class AgnesProductionBridge:
    """Production-facing Agnes capability; ARENA remains the orchestrator."""

    name = "agnes_video"

    def __init__(self, orchestrator: ArenaVideoOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or ArenaVideoOrchestrator()

    def health(self) -> dict[str, Any]:
        return self.orchestrator.agnes.health()

    def submit(self, prompt: str, *, workflow: str = "simple", **options: Any) -> dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            return self._error("Agnes: aucun prompt video fourni.")
        try:
            task = self.orchestrator.generate(prompt, workflow=workflow, **options)
        except (AgnesError, ValueError, TypeError) as exc:
            return self._error(str(exc))
        return self._task_response(task, workflow)

    def status(self, task_id: str) -> dict[str, Any]:
        try:
            task = self.orchestrator.agnes.task(task_id)
        except (AgnesError, ValueError) as exc:
            return self._error(str(exc))
        return self._task_response(task, "status")

    def collect(self, task_id: str, *, filename: str | None = None) -> dict[str, Any]:
        try:
            safe_id = self.orchestrator.agnes._id(task_id)
        except (ValueError, TypeError) as exc:
            return self._error(str(exc))
        safe_name = Path(filename or f"agnes-{safe_id}.mp4").name
        if not safe_name.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
            return self._error("Agnes: extension de sortie video invalide.")
        destination = RENDERED_DIR / safe_name
        try:
            result = self.orchestrator.collect(task_id, destination)
        except (AgnesError, ValueError, OSError) as exc:
            return self._error(str(exc))
        if result.output is None:
            return {
                "statut": "PENDING",
                "message": f"Agnes: tache {result.task.task_id} encore {result.task.status}.",
                "task_id": result.task.task_id,
                "provider": result.provider,
                "etat_provider": result.task.status,
            }
        return {
            "statut": "SUCCESS",
            "message": "Agnes: video terminee et collectee par ARENA.",
            "task_id": result.task.task_id,
            "provider": result.provider,
            "preuve": str(result.output),
        }

    @staticmethod
    def _task_response(task: AgnesTask, workflow: str) -> dict[str, Any]:
        status = task.status.lower()
        return {
            "statut": "SUCCESS" if status in _SUCCESS else "SUBMITTED",
            "message": f"Agnes: tache {task.task_id} {task.status}.",
            "task_id": task.task_id,
            "provider": "agnes",
            "workflow": workflow,
            "etat_provider": task.status,
        }

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return {"statut": "ERROR", "message": message, "provider": "agnes"}


def agnes_capability(orchestrator: ArenaVideoOrchestrator | None = None) -> dict[str, Any]:
    engine = orchestrator or ArenaVideoOrchestrator()
    return {
        "name": "agnes_video",
        "provider": engine.agnes.name,
        "category": "video",
        "modes": ["simple", "creative", "manuscript", "poetry", "anchor"],
        "standalone": True,
        "composable": True,
        "outputs": ["video", "artifacts"],
        "can_postprocess_with_arena": True,
    }


__all__ = [
    "AgnesError", "AgnesProductionBridge", "AgnesTask", "AgnesVideoProvider",
    "ArenaVideoOrchestrator", "FFmpegTool", "VideoWorkflowResult", "agnes_capability",
]
