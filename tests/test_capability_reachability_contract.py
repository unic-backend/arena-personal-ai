from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_chat_dispatch_keeps_core_capabilities_reachable():
    source = _source("apps/backend/routers/chat.py")
    required_links = {
        "documents": 'elif intent == "RAG_DOCS"',
        "vision": 'elif intent == "VISION"',
        "audio": 'elif intent == "AUDIO"',
        "montage": 'elif intent == "MONTAGE"',
        "video_project": 'elif intent == "VIDEO_PROJET"',
        "memory": "memory.add_chat_message(",
        "document_export": "return await _joindre_document(request.prompt, reponse)",
    }
    missing = [name for name, marker in required_links.items() if marker not in source]
    assert not missing, f"User-facing capabilities disconnected from chat: {missing}"


def test_pwa_uses_the_same_dispatch_path_as_chat():
    source = _source("apps/backend/routers/pwa_gateway.py")
    assert "dispatch_request," in source


def test_document_export_is_not_pdf_only():
    source = _source("apps/backend/routers/chat.py")
    for target in ("pdf", "docx", "md", "txt", "html"):
        assert f'\"{target}\"' in source
    assert 'registre.executer, "file_conversion", "rediger"' in source


def test_orphan_scanner_starts_from_real_user_entrypoints():
    source = _source("scripts/orphelins.py")
    for entrypoint in (
        "apps.backend.main",
        "apps.backend.routers.pwa_gateway",
        "apps.backend.runtime",
        "agents.orchestrator.orchestrator_agent",
    ):
        assert entrypoint in source
