import pytest

from tools.video import AgnesError, AgnesVideoProvider


def test_agnes_task_requires_real_id():
    with pytest.raises(AgnesError, match="task id"):
        AgnesVideoProvider._task({"status": "created"})


def test_agnes_task_preserves_provider_payload():
    payload = {"id": "abc", "status": "queued", "extra": 7}
    task = AgnesVideoProvider._task(payload)
    assert task.task_id == "abc"
    assert task.status == "queued"
    assert task.payload is payload
