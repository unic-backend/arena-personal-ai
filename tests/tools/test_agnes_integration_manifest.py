import json
from pathlib import Path


def test_agnes_manifest_declares_composable_provider():
    manifest = json.loads(Path("tools/video/AGNES_INTEGRATION.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == "agnes"
    assert manifest["license"] == "MIT"
    assert manifest["composition"]["standalone"] is True
    assert manifest["composition"]["arena_postprocessing"] is True
    assert "multi_scene" in manifest["capabilities"]
