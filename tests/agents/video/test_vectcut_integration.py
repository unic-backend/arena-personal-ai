import pytest

from agents.video.production_agent import VideoProductionAgent
from core.production.plan_video import CAPACITES_ECRITURE, CAPACITES_VIDEO


class Modele:
    async def is_available(self):
        return True

    async def generate(self, **kwargs):
        return "[]"


class Registre:
    def __init__(self):
        self.appels = []

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append((connecteur, capacite, parametres))
        return {"statut": "NEEDS_CONFIRMATION", "message": "confirmation requise"}


def test_vectcut_est_une_capacite_video_ecriture():
    assert "vectcut" in CAPACITES_VIDEO
    assert "vectcut" in CAPACITES_ECRITURE


@pytest.mark.asyncio
async def test_agent_video_route_vectcut_par_le_registre():
    registre = Registre()
    agent = VideoProductionAgent(provider=Modele(), registre=registre)

    resultat = await agent._appeler_vectcut({
        "outil": "add_text",
        "arguments": {"text": "Arena", "start": 0, "end": 2},
    })

    assert resultat["statut"] == "NEEDS_CONFIRMATION"
    assert registre.appels == [
        ("vectcut", "add_text", {"text": "Arena", "start": 0, "end": 2})
    ]


@pytest.mark.asyncio
async def test_agent_video_refuse_arguments_vectcut_non_objet():
    agent = VideoProductionAgent(provider=Modele(), registre=Registre())
    with pytest.raises(RuntimeError, match="arguments doit etre un objet"):
        await agent._appeler_vectcut({"outil": "add_text", "arguments": "non"})
