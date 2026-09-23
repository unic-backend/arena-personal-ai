from __future__ import annotations

import json
from email.message import Message

import pytest

from tools.video import AgnesError, AgnesVideoProvider


class FakeResponse:
    def __init__(self, payload, content_type="application/json"):
        self.payload = payload
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode()


def test_simple_task_uses_agnes_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode()
        captured["timeout"] = timeout
        return FakeResponse({"task_id": "abc", "status": "queued"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AgnesVideoProvider("http://agnes:8765", timeout=4)
    task = provider.create_simple("Dakar skyline", duration=8, resolution="16:9")

    assert captured["url"] == "http://agnes:8765/api/tasks/simple"
    assert "prompt=Dakar+skyline" in captured["body"]
    assert captured["timeout"] == 4
    assert task.task_id == "abc"
    assert task.status == "queued"


def test_provider_can_return_binary_video(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"video", "video/mp4"),
    )
    provider = AgnesVideoProvider()
    target = provider.download_video("task-1", tmp_path / "out.mp4")
    assert target.read_bytes() == b"video"


def test_task_id_rejects_path_traversal():
    with pytest.raises(ValueError):
        AgnesVideoProvider._id("../../secret")


def test_invalid_task_response_is_explicit():
    with pytest.raises(AgnesError):
        AgnesVideoProvider._task({"status": "queued"})
