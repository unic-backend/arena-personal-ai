import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from core.actions.resultat import succes
from tools.atelier import Atelier


class ModeleScripte:
    def __init__(self, *reponses):
        self.reponses = list(reponses)

    async def is_available(self):
        return True

    async def generate(self, prompt, system_prompt=None):
        return self.reponses.pop(0)


class FauxPresentation:
    def __init__(self):
        self.appels = []

    def executer(self, capacite, **parametres):
        self.appels.append((capacite, parametres))
        return succes("generer", "presentation", "ok", preuve="a.pptx",
                      url="/media/rendered/presentations/a.pptx", slides=1)


@pytest.mark.asyncio
async def test_dioumtoukay_appelle_le_connecteur_presentation(tmp_path):
    connecteur = FauxPresentation()
    plan = '{"titre":"Arena","slides":[{"titre":"Intro","puces":["A"]}]}'
    agent = DioumtoukayAgent(
        provider=ModeleScripte(
            f"ACTION: presentation_generer\nCONTENU:\n{plan}\nFIN",
            "ACTION: terminer\nCONTENU:\nprésentation générée\nFIN",
        ),
        atelier=Atelier(racine=tmp_path),
        connecteur_presentation=connecteur,
    )
    resultat = await agent.run("Fais-moi une présentation Arena")
    assert resultat["actions"][0]["ok"] is True
    assert connecteur.appels == [("generer", {"plan": plan})]
