"""RepoEngineerAgent : analyse d'architecture en lecture seule.

Le point qui compte : il lit le dépôt et propose, il n'écrit jamais.
"""
import pytest

from agents.repo_engineer.repo_engineer_agent import RepoEngineerAgent

ARBRE = ["apps/", "apps/backend/", "core/", "core/agent/", "tools/"]


@pytest.fixture
def agent(provider_factory, monkeypatch):
    agent = RepoEngineerAgent(provider=provider_factory("Plan : ajouter core/audit/."), memory=None)
    monkeypatch.setattr(agent.repo_tool, "get_tree", lambda max_depth=3: ARBRE)
    return agent


async def test_la_structure_lue_est_transmise_au_modele(agent):
    await agent.run("Ajoute un module de logs d'audit")

    prompt = agent.provider.appels[0]["prompt"]
    for entree in ARBRE:
        assert entree in prompt


async def test_le_plan_est_renvoye_et_la_reserve_de_lecture_seule_affichee(agent):
    res = await agent.run("Ajoute un module de logs d'audit")

    assert res["status"] == "success"
    assert res["architecture_plan"] == "Plan : ajouter core/audit/."
    assert "ne modifie aucun fichier" in res["response"]


async def test_l_agent_n_ecrit_rien_sur_le_disque(agent, monkeypatch):
    """Lecture seule : toute écriture doit être absente, pas seulement annoncée."""
    def interdit(*args, **kwargs):
        raise AssertionError("RepoEngineerAgent a tenté d'écrire un fichier.")

    monkeypatch.setattr(agent.repo_tool, "apply_patch", interdit)
    monkeypatch.setattr("pathlib.Path.write_text", interdit)
    monkeypatch.setattr("pathlib.Path.write_bytes", interdit)

    assert (await agent.run("Modifie le fichier main.py"))["status"] == "success"
