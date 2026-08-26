"""PublisherAgent : la publication réelle est bloquée, et elle doit le rester.

Le connecteur TikTok est un simulateur ; aucune requête ne sort d'ici.
"""
import pytest

from agents.publisher.publisher_agent import PublisherAgent


@pytest.fixture
def video_factice(tmp_path):
    """Un fichier qui existe, sans quoi l'agent s'arrête avant la vérification de sécurité."""
    chemin = tmp_path / "video.mp4"
    chemin.write_bytes(b"pas une vraie video, mais le fichier existe")
    return chemin


async def test_sans_video_l_agent_refuse_avant_toute_publication(fake_provider):
    agent = PublisherAgent(provider=fake_provider)

    res = await agent.run("Les tendances tech", context={"video_path": "/chemin/inexistant.mp4"})

    assert res["status"] == "error"
    assert fake_provider.appels == []


async def test_sans_contexte_l_agent_refuse(fake_provider):
    agent = PublisherAgent(provider=fake_provider)

    assert (await agent.run("Les tendances tech"))["status"] == "error"


async def test_la_permission_publish_est_bloquee_et_la_publication_simulee(
    provider_factory, video_factice
):
    provider = provider_factory("Titre accrocheur\nDescription\n#tech #senegal")
    agent = PublisherAgent(provider=provider)
    assert agent.permissions.is_allowed("PUBLISH") is False, "PUBLISH doit rester bloqué"

    res = await agent.run("Les tendances tech", context={"video_path": str(video_factice)})

    assert res["status"] == "success"
    assert "MODE SÉCURITÉ ACTIF" in res["response"]
    assert "SIMULATION TIKTOK" in res["response"]
    assert "Titre accrocheur" in res["response"]


async def test_la_publication_reelle_n_est_pas_implementee(
    provider_factory, video_factice, monkeypatch
):
    """Même permission accordée, rien ne part : le chemin réel n'existe pas."""
    agent = PublisherAgent(provider=provider_factory())
    monkeypatch.setattr(agent.permissions, "is_allowed", lambda nom: True)

    res = await agent.run("Sujet", context={"video_path": str(video_factice)})

    assert res["status"] == "error"
    assert "non implémentée" in res["response"]
