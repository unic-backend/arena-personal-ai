from tools.video import agnes_capability


class FakeProvider:
    name = "agnes"


class FakeOrchestrator:
    agnes = FakeProvider()


def test_agnes_remains_standalone_and_composable():
    capability = agnes_capability(FakeOrchestrator())
    assert capability["standalone"] is True
    assert capability["composable"] is True
    assert capability["can_postprocess_with_arena"] is True
    assert set(capability["modes"]) == {"simple", "creative", "manuscript", "poetry", "anchor"}
