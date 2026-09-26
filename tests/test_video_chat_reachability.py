from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_video_project_is_reachable_from_chat_dispatch():
    source = (ROOT / "apps/backend/routers/chat.py").read_text(encoding="utf-8")
    assert 'elif intent == "VIDEO_PROJET"' in source
    assert "video_production_agent.run(" in source
    assert '"references": medias_montables(request.video_path)' in source


def test_video_space_allows_full_project_routing():
    from agents.orchestrator.orchestrator_agent import FAMILLE_PAR_ESPACE

    source = (ROOT / "agents/orchestrator/orchestrator_agent.py").read_text(encoding="utf-8")
    # La famille reelle, pas sa chaine exacte : la figer interdisait d'y
    # ajouter STUDIO et TREND_SEARCH (DEC-0140). Les cinq restent exiges.
    assert {"VIDEO_ANALYSIS", "MONTAGE", "VIDEO_PROJET", "AUDIO", "VISION"} <= FAMILLE_PAR_ESPACE["video"]
    assert '"VIDEO_PROJET"' in source
    assert "VIDEO_PROJET = (" in source


def test_pwa_gateway_uses_shared_chat_dispatch():
    source = (ROOT / "apps/backend/routers/pwa_gateway.py").read_text(encoding="utf-8")
    assert "dispatch_request," in source
