from tools.video import AgnesProductionBridge, AgnesTask


class Provider:
    name = "agnes"

    def task(self, task_id):
        return AgnesTask(task_id, "completed", {"id": task_id, "status": "completed"})


class Orchestrator:
    agnes = Provider()


def test_bridge_status_reports_completed_task_without_fake_artifact():
    result = AgnesProductionBridge(Orchestrator()).status("done-1")
    assert result["statut"] == "SUCCESS"
    assert result["task_id"] == "done-1"
    assert "preuve" not in result
