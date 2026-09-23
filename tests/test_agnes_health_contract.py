from tools.video import AgnesError, AgnesVideoProvider


def test_agnes_health_reports_unavailable_instead_of_fake_success(monkeypatch):
    provider = AgnesVideoProvider("http://127.0.0.1:1")

    def fail(*args, **kwargs):
        raise AgnesError("offline")

    monkeypatch.setattr(provider, "_request", fail)
    result = provider.health()
    assert result["available"] is False
    assert result["provider"] == "agnes"
    assert "offline" in result["reason"]
