from tools.video import AgnesProductionBridge


class Provider:
    name = "agnes"

    @staticmethod
    def _id(task_id):
        if ".." in task_id:
            raise ValueError("invalid Agnes task id")
        return task_id


class Orchestrator:
    agnes = Provider()


def test_bridge_rejects_unsafe_task_id_before_collection():
    result = AgnesProductionBridge(Orchestrator()).collect("../bad")
    assert result["statut"] == "ERROR"
    assert "invalid" in result["message"]
