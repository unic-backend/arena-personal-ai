from tools.video import AgnesProductionBridge, AgnesTask


class PendingAgnes:
    name = "agnes"

    @staticmethod
    def _id(task_id):
        return task_id

    def task(self, task_id):
        return AgnesTask(task_id, "running", {"id": task_id, "status": "running"})


class PendingOrchestrator:
    def __init__(self):
        self.agnes = PendingAgnes()

    def collect(self, task_id, destination):
        from tools.video import VideoWorkflowResult
        return VideoWorkflowResult("agnes", self.agnes.task(task_id))


def test_pending_agnes_never_exposes_preuve():
    result = AgnesProductionBridge(PendingOrchestrator()).collect("job-1")
    assert result["statut"] == "PENDING"
    assert "preuve" not in result
