import pytest

from tools.video import AgnesVideoProvider, ArenaVideoOrchestrator


def test_task_id_rejects_path_traversal():
    with pytest.raises(ValueError):
        AgnesVideoProvider._id("../secret")
    with pytest.raises(ValueError):
        AgnesVideoProvider._id("folder/task")


def test_orchestrator_rejects_unknown_workflow_before_network():
    orchestrator = ArenaVideoOrchestrator(agnes=object())
    with pytest.raises(ValueError, match="unsupported video workflow"):
        orchestrator.generate("hello", workflow="unknown")
