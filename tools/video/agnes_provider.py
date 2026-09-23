"""Agnes Video Generator adapter for ARENA's existing video toolbox.

This module intentionally keeps Agnes behind a provider boundary instead of
forking its application into ARENA. It lets the orchestrator use Agnes alone
or compose it with ARENA's image, audio, subtitle and FFmpeg tools.

Upstream: https://github.com/lcy362/agnes-video-generator (MIT)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AgnesError(RuntimeError):
    """Raised when the Agnes service cannot satisfy a request."""


@dataclass(frozen=True)
class AgnesTask:
    task_id: str
    status: str
    payload: dict[str, Any]


class AgnesVideoProvider:
    """Small stdlib-only client for a self-hosted Agnes Video Generator.

    The provider does not own orchestration. ARENA can call individual Agnes
    capabilities and combine their artifacts with its native tools.
    """

    name = "agnes"

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.getenv("AGNES_VIDEO_URL", "http://127.0.0.1:8765")).rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        fields: dict[str, Any] | None = None,
    ) -> Any:
        data = None
        headers: dict[str, str] = {"Accept": "application/json"}
        if fields is not None:
            encoded = {
                key: json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)
                for key, value in fields.items()
                if value is not None
            }
            data = urllib.parse.urlencode(encoded).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
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
        """Return service/config visibility without mutating Agnes state."""
        try:
            config = self._request("GET", "/api/config")
            return {"available": True, "provider": self.name, "config": config}
        except AgnesError as exc:
            return {"available": False, "provider": self.name, "reason": str(exc)}

    def models(self) -> Any:
        return self._request("GET", "/api/models")

    def voices(self) -> Any:
        return self._request("GET", "/api/voices")

    def create_simple(
        self,
        prompt: str,
        *,
        mode: str = "t2v",
        duration: int = 5,
        resolution: str = "768x1152",
    ) -> AgnesTask:
        payload = self._request(
            "POST",
            "/api/tasks/simple",
            fields={
                "prompt": prompt,
                "mode": mode,
                "duration": duration,
                "resolution": resolution,
            },
        )
        return self._task(payload)

    def create_creative(self, **fields: Any) -> AgnesTask:
        return self._task(self._request("POST", "/api/tasks/creative", fields=fields))

    def create_manuscript(self, manuscript_text: str, **fields: Any) -> AgnesTask:
        return self._task(
            self._request(
                "POST",
                "/api/tasks/manuscript",
                fields={"manuscript_text": manuscript_text, **fields},
            )
        )

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
        return AgnesTask(
            task_id=str(task_id),
            status=str(payload.get("status", "created")),
            payload=payload,
        )
