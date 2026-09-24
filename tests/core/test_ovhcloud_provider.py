from core.models.ovhcloud_provider import OVHCloudProvider


def test_ovhcloud_absent_sans_cle():
    provider = OVHCloudProvider(api_key="", model_name="gpt-oss-120b")
    assert provider.configure is False


def test_ovhcloud_reutilise_le_contrat_openai_compatible():
    provider = OVHCloudProvider(
        api_key="test-only",
        model_name="gpt-oss-120b",
        base_url="https://example.invalid/v1",
    )
    assert provider.configure is True
    assert provider.nom == "ovhcloud"
    assert provider.model_name == "gpt-oss-120b"
    assert provider.base_url == "https://example.invalid/v1"
    assert provider._corps("bonjour", "systeme", flux=False) == {
        "model": "gpt-oss-120b",
        "messages": [
            {"role": "system", "content": "systeme"},
            {"role": "user", "content": "bonjour"},
        ],
        "stream": False,
    }
