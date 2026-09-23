from tools.video import AgnesVideoProvider


def test_valid_agnes_task_id_is_preserved():
    assert AgnesVideoProvider._id("task-123_abc") == "task-123_abc"
