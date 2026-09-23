import pytest

from agents.video.production_agent import VideoProductionAgent
from core.agent.capacites import RegistreCapacites


class Provider:
    async def is_available(self): return True
    async def generate(self, **kwargs): return "[]"

class Specialist:
    name = "Specialist"
    async def run(self, user_input, context=None):
        return {"status": "success", "agent": self.name, "response": user_input,
                "origin": (context or {}).get("origine")}

@pytest.mark.asyncio
async def test_video_can_delegate_without_rebuilding_specialist():
    registry = RegistreCapacites()
    specialist = Specialist()
    registry.enregistrer("recherche", specialist)
    agent = VideoProductionAgent(provider=Provider(), collaborateurs=registry)

    result = await agent.demander_specialiste("recherche", "cherche les tendances")

    assert result["status"] == "success"
    assert result["response"] == "cherche les tendances"
    assert result["origin"] == "video_production"
    assert registry._capacites["recherche"] is specialist

@pytest.mark.asyncio
async def test_video_refuses_unknown_specialist_instead_of_guessing():
    agent = VideoProductionAgent(provider=Provider(), collaborateurs=RegistreCapacites())
    result = await agent.demander_specialiste("agent_invente", "fais quelque chose")
    assert result["status"] == "error"
    assert "specialiste inconnu" in result["response"]
