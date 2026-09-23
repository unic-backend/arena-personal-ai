from tools.video import AgnesTask, ArenaVideoOrchestrator


class RecordingProvider:
    name = "agnes"

    def __init__(self):
        self.calls = []

    def _record(self, name, **fields):
        self.calls.append((name, fields))
        return AgnesTask("x", "queued", fields)

    def create_simple(self, prompt, **fields):
        return self._record("simple", prompt=prompt, **fields)

    def create_creative(self, **fields):
        return self._record("creative", **fields)

    def create_manuscript(self, manuscript_text, **fields):
        return self._record("manuscript", manuscript_text=manuscript_text, **fields)

    def create_poetry(self, **fields):
        return self._record("poetry", **fields)

    def create_anchor(self, **fields):
        return self._record("anchor", **fields)


def test_all_declared_agnes_workflows_dispatch():
    provider = RecordingProvider()
    orchestrator = ArenaVideoOrchestrator(provider)
    for workflow in ("simple", "creative", "manuscript", "poetry", "anchor"):
        orchestrator.generate("scene", workflow=workflow)
    assert [name for name, _ in provider.calls] == ["simple", "creative", "manuscript", "poetry", "anchor"]
