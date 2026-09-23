"""Production bridge between ARENA's video workspace and Agnes.

Agnes remains a provider, never a second orchestrator.  This bridge exposes
one small contract that ARENA can call standalone or as one step in a larger
video workflow.  It deliberately returns task metadata at submission time;
it never claims that a video file exists before Agnes reports completion.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from apps.backend.config import RENDERED_DIR
from tools.video import AgnesError, AgnesTask, ArenaVideoOrchestrator


_SUCCESS = {"completed", "complete", "success", "succeeded"}


class AgnesProductionBridge:
    """Safe, injectable Agnes capability for the ARENA video workspace."""

    name = "agnes_video"

    def __init__(self, orchestrator: Optional[ArenaVideoOrchestrator] = None) -> None:
        self.orchestrator = orchestrator or ArenaVideoOrchestrator()

    def health(self) -> Dict[str, Any]:
        """Report measured provider availability; never simulate readiness."""
        return self.orchestrator.agnes.health()

    def submit(self, prompt: str, *, workflow: str = "simple", **options: Any) -> Dict[str, Any]:
        """Submit a generation and return a task id, not a fictitious file."""
        prompt = (prompt or "").strip()
        if not prompt:
            return self._error("Agnes: aucun prompt video fourni.")
        try:
            task = self.orchestrator.generate(prompt, workflow=workflow, **options)
        except (AgnesError, ValueError, TypeError) as exc:
            return self._error(str(exc))
        return self._task_response(task, workflow)

    def status(self, task_id: str) -> Dict[str, Any]:
        """Read a real Agnes task state without downloading anything."""
        try:
            task = self.orchestrator.agnes.task(task_id)
        except (AgnesError, ValueError) as exc:
            return self._error(str(exc))
        return self._task_response(task, "status")

    def collect(self, task_id: str, *, filename: Optional[str] = None) -> Dict[str, Any]:
        """Download only a task Agnes itself reports as completed.

        The destination is always under ARENA's rendered directory.  A caller
        cannot inject an arbitrary output path through the model/planner.
        """
        safe_id = self.orchestrator.agnes._id(task_id)
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
    def _task_response(task: AgnesTask, workflow: str) -> Dict[str, Any]:
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
    def _error(message: str) -> Dict[str, Any]:
        return {"statut": "ERROR", "message": message, "provider": "agnes"}


__all__ = ["AgnesProductionBridge"]
