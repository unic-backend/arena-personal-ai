from tools.video import AgnesProductionBridge, AgnesVideoProvider


def test_agnes_capability_has_stable_identity():
    assert AgnesVideoProvider.name == "agnes"
    assert AgnesProductionBridge.name == "agnes_video"
