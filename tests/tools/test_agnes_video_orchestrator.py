from pathlib import Path

import pytest

from tools.video import AgnesTask, ArenaVideoOrchestrator


class FakeAgnes:
    name = "agnes"

    def create_simple(self, prompt, **options):
        return AgnesTask("one", "queued", {"prompt": prompt, **options})

    def create_creative(self, **fields):
        return AgnesTask("creative", "queued", fields)

    def create_manuscript(self, text, **fields):
        return AgnesTask("manuscript", "queued", {"text": text, **fields})

    def create_poetry(self, **fields):
        return AgnesTask("poetry", "queued", fields)

    def create_anchor(self, **fields):
        return AgnesTask("anchor", "queued", fields)

    def task(self, task_id):
        return AgnesTask(task_id, "completed", {})

    def download_video(self, task_id, destination):
        path = Path(destination)
        path.write_bytes(task_id.encode())
        return path


def test_orchestrator_routes_modes():
    orchestrator = ArenaVideoOrchestrator(FakeAgnes())
    assert orchestrator.generate("hello").task_id == "one"
    assert orchestrator.generate("hello", workflow="creative").task_id == "creative"
    assert orchestrator.generate("hello", workflow="manuscript").task_id == "manuscript"
    assert orchestrator.generate("hello", workflow="poetry").task_id == "poetry"
    assert orchestrator.generate("hello", workflow="anchor").task_id == "anchor"
    with pytest.raises(ValueError):
        orchestrator.generate("hello", workflow="unknown")


def test_completed_agnes_video_can_enter_arena_postprocessing(tmp_path):
    orchestrator = ArenaVideoOrchestrator(FakeAgnes())
    called = []

    def postprocess(path):
        called.append(path)
        return {"subtitles": True, "ffmpeg": True}

    result = orchestrator.collect("done", tmp_path / "done.mp4", postprocessor=postprocess)
    assert result.output is not None
    assert result.output.read_bytes() == b"done"
    assert called == [result.output]
    assert result.postprocess == {"subtitles": True, "ffmpeg": True}
