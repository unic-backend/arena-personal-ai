from tools.video import AgnesProductionBridge


class FakeAgnes:
    name = "agnes"

    @staticmethod
    def _id(task_id):
        return task_id


class FakeOrchestrator:
    agnes = FakeAgnes()


def test_agnes_collect_rejects_non_video_filename_without_provider_call():
    result = AgnesProductionBridge(FakeOrchestrator()).collect("task-1", filename="result.txt")
    assert result["statut"] == "ERROR"
    assert "extension" in result["message"].lower()
