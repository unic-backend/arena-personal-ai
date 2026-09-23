"""Composition layer between Agnes and ARENA's native video tools."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from tools.video.agnes_provider import AgnesTask, AgnesVideoProvider


@dataclass(frozen=True)
class VideoWorkflowResult:
    provider: str
    task: AgnesTask
    output: Path | None = None
    postprocess: dict[str, Any] | None = None


class ArenaVideoOrchestrator:
    """Use Agnes alone or hand its output to another ARENA video stage.

    ``postprocessor`` is deliberately injected: FFmpeg/subtitle/audio workflows
    keep their own contracts and can evolve independently from Agnes.
    """

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

    def collect(
        self,
        task_id: str,
        destination: str | Path,
        *,
        postprocessor: Callable[[Path], dict[str, Any] | None] | None = None,
    ) -> VideoWorkflowResult:
        task = self.agnes.task(task_id)
        if task.status.lower() not in {"completed", "complete", "success", "succeeded"}:
            return VideoWorkflowResult(provider=self.agnes.name, task=task)
        output = self.agnes.download_video(task_id, destination)
        postprocess = postprocessor(output) if postprocessor else None
        return VideoWorkflowResult(
            provider=self.agnes.name,
            task=task,
            output=output,
            postprocess=postprocess,
        )
