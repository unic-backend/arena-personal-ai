"""Vérifie le double de fournisseur du socle de tests.

Un double qui ment rend tous les tests qui s'appuient dessus sans valeur : il est
donc testé comme le reste.
"""
import pytest

from tests.conftest import FakeProvider


async def test_reponses_servies_dans_l_ordre(provider_factory):
    provider = provider_factory("première", "deuxième")

    assert await provider.generate("q1") == "première"
    assert await provider.generate("q2") == "deuxième"


async def test_appel_en_trop_leve_une_erreur_explicite(provider_factory):
    provider = provider_factory("unique")
    await provider.generate("q1")

    with pytest.raises(AssertionError, match="1 réponse"):
        await provider.generate("q2")


async def test_les_prompts_envoyes_sont_enregistres(fake_provider):
    await fake_provider.generate("Bonjour", system_prompt="Tu es ARENA.")

    assert fake_provider.appels == [{"prompt": "Bonjour", "system_prompt": "Tu es ARENA."}]


async def test_le_streaming_rejoue_la_reponse_entiere(provider_factory):
    provider = provider_factory("un deux trois")

    jetons = [jeton async for jeton in provider.generate_stream("q")]

    assert len(jetons) == 3
    assert "".join(jetons).strip() == "un deux trois"


async def test_disponibilite_pilotable():
    assert await FakeProvider().is_available() is True
    assert await FakeProvider(disponible=False).is_available() is False


async def test_aucun_reseau_n_est_ouvert(fake_provider, monkeypatch):
    """Garde-fou : le double ne doit jamais ouvrir de connexion."""
    import socket

    def interdit(*args, **kwargs):
        raise AssertionError("Le FakeProvider a tenté d'ouvrir une connexion réseau.")

    monkeypatch.setattr(socket.socket, "connect", interdit)
    assert await fake_provider.generate("q") == "Réponse simulée d'ARENA."


def test_memoire_est_jetable_et_hors_du_depot(memoire, tmp_path):
    memoire.add_chat_message(session_id="s", role="user", content="salut")

    assert memoire.db_path.parent == tmp_path
    assert [m["content"] for m in memoire.get_recent_history("s")] == ["salut"]
