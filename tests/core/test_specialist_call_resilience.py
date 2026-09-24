import asyncio
from typing import Any, Dict, Optional

import pytest

import core.agent.base_agent as base_module
from core.agent.base_agent import BaseAgent
from core.agent.capacites import RegistreCapacites


class _Provider:
    pass


class _Agent(BaseAgent):
    def __init__(self, nom: str):
        super().__init__(nom, "test", _Provider())

    async def run(
        self, user_input: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return {"status": "success", "agent": self.name, "response": user_input}


class _Lent(_Agent):
    async def run(self, user_input: str, context=None):
        await asyncio.sleep(1)
        return await super().run(user_input, context)


class _Casse(_Agent):
    async def run(self, user_input: str, context=None):
        raise RuntimeError("secret interne qui ne doit pas remonter")


@pytest.mark.asyncio
async def test_un_specialiste_qui_expire_ne_bloque_pas_agent(monkeypatch):
    registre = RegistreCapacites()
    appelant = _Agent("orchestrator")
    lent = _Lent("researcher")
    registre.enregistrer("researcher", lent)
    appelant.collaborateurs = registre
    monkeypatch.setattr(base_module, "DELAI_SPECIALISTE_SECONDES", 0.01)

    resultat = await appelant.demander_specialiste("researcher", "cherche ceci")

    assert resultat["status"] == "error"
    assert resultat["specialiste"] == "researcher"
    assert "delai" in resultat["response"].lower()


@pytest.mark.asyncio
async def test_panne_specialiste_est_isolee_et_ne_fuit_pas_detail():
    registre = RegistreCapacites()
    appelant = _Agent("orchestrator")
    registre.enregistrer("researcher", _Casse("researcher"))
    appelant.collaborateurs = registre

    resultat = await appelant.demander_specialiste("researcher", "cherche ceci")

    assert resultat["status"] == "error"
    assert resultat["specialiste"] == "researcher"
    assert "RuntimeError" in resultat["response"]
    assert "secret interne" not in resultat["response"]


@pytest.mark.asyncio
async def test_specialiste_sain_reste_appele_reellement():
    registre = RegistreCapacites()
    appelant = _Agent("orchestrator")
    registre.enregistrer("researcher", _Agent("researcher"))
    appelant.collaborateurs = registre

    resultat = await appelant.demander_specialiste("researcher", "cherche ceci")

    assert resultat == {
        "status": "success", "agent": "researcher", "response": "cherche ceci"
    }


@pytest.mark.asyncio
async def test_agent_ne_se_delegue_jamais_a_lui_meme():
    registre = RegistreCapacites()
    appelant = _Agent("orchestrator")
    registre.enregistrer("orchestrator", appelant)
    appelant.collaborateurs = registre

    resultat = await appelant.demander_specialiste("orchestrator", "continue")

    assert resultat["status"] == "error"
    assert resultat["agent"] == "orchestrator"
    assert "lui-meme" in resultat["response"]
