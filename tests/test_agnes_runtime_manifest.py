import json
from pathlib import Path


def test_agnes_runtime_manifest_keeps_arena_as_orchestrator():
    data = json.loads(Path("tools/video/AGNES_RUNTIME.json").read_text(encoding="utf-8"))
    assert data["capability"] == "agnes_video"
    assert data["standalone"] is True
    assert data["composable"] is True
    assert data["nested_orchestrator"] is False
    assert data["artifact_requires_completed_task"] is True
