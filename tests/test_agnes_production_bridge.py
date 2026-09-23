from pathlib import Path

from tools.video import AgnesProductionBridge, AgnesTask, VideoWorkflowResult


class FakeAgnes:
    name = "agnes"

    def __init__(self, status="queued"):
        self.current = AgnesTask("task-42", status, {"id": "task-42", "status": status})

    def health(self):
        return {"available": True, "provider": "agnes"}

    def task(self, task_id):
        assert task_id == "task-42"
        return self.current

    @staticmethod
    def _id(task_id):
        return task_id


class FakeOrchestrator:
    def __init__(self, status="queued", output=None):
        self.agnes = FakeAgnes(status)
        self.output = output
        self.generated = []
        self.destination = None

    def generate(self, prompt, *, workflow="simple", **options):
        self.generated.append((prompt, workflow, options))
        return self.agnes.current

    def collect(self, task_id, destination):
        self.destination = Path(destination)
        if self.output is None:
            return VideoWorkflowResult("agnes", self.agnes.current)
        return VideoWorkflowResult("agnes", self.agnes.current, Path(self.output))


def test_submit_exposes_real_task_without_fake_file():
    orchestrator = FakeOrchestrator()
    bridge = AgnesProductionBridge(orchestrator)
    result = bridge.submit("Dakar au lever du soleil", workflow="creative", duration=8)
    assert result["statut"] == "SUBMITTED"
    assert result["task_id"] == "task-42"
    assert "preuve" not in result
    assert orchestrator.generated == [("Dakar au lever du soleil", "creative", {"duration": 8})]


def test_submit_rejects_empty_prompt():
    assert AgnesProductionBridge(FakeOrchestrator()).submit("   ")["statut"] == "ERROR"


def test_collect_does_not_claim_file_while_task_pending():
    result = AgnesProductionBridge(FakeOrchestrator(status="running")).collect("task-42")
    assert result["statut"] == "PENDING"
    assert "preuve" not in result


def test_collect_returns_proof_only_for_collected_artifact(tmp_path):
    output = tmp_path / "final.mp4"
    output.write_bytes(b"video")
    result = AgnesProductionBridge(FakeOrchestrator(status="completed", output=output)).collect("task-42")
    assert result["statut"] == "SUCCESS"
    assert result["preuve"] == str(output)


def test_collect_sanitizes_requested_filename(monkeypatch, tmp_path):
    import tools.video as module

    monkeypatch.setattr(module, "RENDERED_DIR", tmp_path)
    orchestrator = FakeOrchestrator(status="completed", output=tmp_path / "safe.mp4")
    result = AgnesProductionBridge(orchestrator).collect("task-42", filename="../../escape.mp4")
    assert result["statut"] == "SUCCESS"
    assert orchestrator.destination == tmp_path / "escape.mp4"


def test_health_is_measured_from_provider():
    assert AgnesProductionBridge(FakeOrchestrator()).health()["available"] is True
