from tools.video import AgnesVideoProvider


def test_agnes_default_url_is_local(monkeypatch):
    monkeypatch.delenv("AGNES_VIDEO_URL", raising=False)
    assert AgnesVideoProvider().base_url == "http://127.0.0.1:8765"
