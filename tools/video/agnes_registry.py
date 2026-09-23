"""Machine-readable Agnes capability descriptor for ARENA orchestration."""
from __future__ import annotations

from typing import Any

from tools.video.agnes_orchestrator import ArenaVideoOrchestrator


def agnes_capability(orchestrator: ArenaVideoOrchestrator | None = None) -> dict[str, Any]:
    """Describe the provider without requiring the Agnes service to be online."""
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
