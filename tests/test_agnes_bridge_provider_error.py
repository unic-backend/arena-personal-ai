from tools.video import AgnesError, AgnesProductionBridge


class Provider:
    name = "agnes"

    @staticmethod
    def _id(task_id):
        return task_id

    def task(self, task_id):
        raise AgnesError("service offline")


class Orchestrator:
    agnes = Provider()


def test_status_surfaces_provider_failure_without_success():
    result = AgnesProductionBridge(Orchestrator()).status("job")
    assert result["statut"] == "ERROR"
    assert "offline" in result["message"]
