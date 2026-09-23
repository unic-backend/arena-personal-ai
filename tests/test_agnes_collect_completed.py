from pathlib import Path

from tools.video import AgnesTask, ArenaVideoOrchestrator


class CompletedProvider:
    name = "agnes"

    def __init__(self, tmp_path):
        self.tmp_path = tmp_path

    def task(self, task_id):
        return AgnesTask(task_id, "completed", {"id": task_id, "status": "completed"})

    def download_video(self, task_id, destination):
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"video")
        return target


def test_collect_completed_task_creates_real_output(tmp_path):
    orchestrator = ArenaVideoOrchestrator(CompletedProvider(tmp_path))
    destination = tmp_path / "rendered" / "result.mp4"
    result = orchestrator.collect("job-9", destination)
    assert result.output == destination
    assert destination.is_file()
