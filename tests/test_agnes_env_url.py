from tools.video import AgnesVideoProvider


def test_agnes_url_can_be_configured(monkeypatch):
    monkeypatch.setenv("AGNES_VIDEO_URL", "http://agnes.internal:9000/")
    assert AgnesVideoProvider().base_url == "http://agnes.internal:9000"
