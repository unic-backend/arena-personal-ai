"""CoderAgent : génération de code, exécution en bac à sable, et refus.

Hors ligne, le fournisseur est scripté et le bac à sable indisponible — ce qui est
précisément le cas que l'agent doit gérer sans exécuter quoi que ce soit.
"""
import pytest

from agents.coder.coder_agent import CoderAgent

CODE_GENERE = "```python\nprint(sum(range(0, 101, 2)))\n```"


@pytest.fixture
def agent_sans_bac_a_sable(fake_provider, monkeypatch):
    """Agent dont le bac à sable est indisponible et le repli non autorisé."""
    monkeypatch.delenv("ALLOW_UNSAFE_EXEC", raising=False)
    agent = CoderAgent(provider=fake_provider, memory=None)
    monkeypatch.setattr(agent.interpreter, "docker_available", False)
    return agent


async def test_sans_bac_a_sable_l_agent_refuse_au_lieu_d_executer(provider_factory, monkeypatch):
    monkeypatch.delenv("ALLOW_UNSAFE_EXEC", raising=False)
    provider = provider_factory(CODE_GENERE)
    agent = CoderAgent(provider=provider, memory=None)
    monkeypatch.setattr(agent.interpreter, "docker_available", False)

    res = await agent.run("Somme des nombres pairs de 1 à 100")

    assert res["status"] == "refused"
    assert res["sandbox_mode"] == "REFUSED"
    assert "Exécution refusée" in res["response"]


async def test_un_refus_ne_declenche_pas_d_auto_correction(provider_factory, monkeypatch):
    """Corriger un code qui n'a jamais tourné n'a aucun sens, et coûte deux appels au modèle."""
    monkeypatch.delenv("ALLOW_UNSAFE_EXEC", raising=False)
    provider = provider_factory(CODE_GENERE)  # une seule réponse scriptée
    agent = CoderAgent(provider=provider, memory=None)
    monkeypatch.setattr(agent.interpreter, "docker_available", False)

    await agent.run("Somme des nombres pairs")

    # Un deuxième appel aurait levé une AssertionError du FakeProvider.
    assert len(provider.appels) == 1


async def test_un_code_valide_est_execute_et_sa_sortie_remontee(provider_factory, monkeypatch):
    """Repli explicitement autorisé : on mesure le chemin nominal de bout en bout."""
    monkeypatch.setenv("ALLOW_UNSAFE_EXEC", "true")
    provider = provider_factory("```python\nprint(2 + 2)\n```")
    agent = CoderAgent(provider=provider, memory=None)
    monkeypatch.setattr(agent.interpreter, "docker_available", False)

    res = await agent.run("Additionne 2 et 2")

    assert res["status"] == "success"
    assert res["stdout"] == "4"
    assert res["auto_corrected"] is False
    assert res["attempts"] == 1


async def test_un_code_faux_est_corrige_puis_reexecute(provider_factory, monkeypatch):
    monkeypatch.setenv("ALLOW_UNSAFE_EXEC", "true")
    provider = provider_factory(
        "```python\nprint(10 / 0)\n```",        # premier jet : erreur
        "```python\nprint('corrige')\n```",     # correction proposée
    )
    agent = CoderAgent(provider=provider, memory=None)
    monkeypatch.setattr(agent.interpreter, "docker_available", False)

    res = await agent.run("Divise 10 par 0")

    assert res["status"] == "success"
    assert res["auto_corrected"] is True
    assert res["attempts"] == 2
    assert "ZeroDivisionError" in provider.appels[1]["prompt"]


async def test_l_auto_correction_s_arrete_apres_deux_essais(provider_factory, monkeypatch):
    monkeypatch.setenv("ALLOW_UNSAFE_EXEC", "true")
    provider = provider_factory(*["```python\nprint(1 / 0)\n```"] * 3)
    agent = CoderAgent(provider=provider, memory=None)
    monkeypatch.setattr(agent.interpreter, "docker_available", False)

    res = await agent.run("Code impossible à corriger")

    assert res["status"] == "error"
    assert res["attempts"] == 3
    assert provider.reponses_restantes == 0
