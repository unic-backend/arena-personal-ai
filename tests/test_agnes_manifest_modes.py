import json
from pathlib import Path

from tools.video import agnes_capability


class Provider:
    name = "agnes"


class Orchestrator:
    agnes = Provider()


def test_manifest_modes_match_public_capability():
    manifest = json.loads(Path("tools/video/AGNES_RUNTIME.json").read_text(encoding="utf-8"))
    capability = agnes_capability(Orchestrator())
    assert manifest["workflows"] == capability["modes"]
