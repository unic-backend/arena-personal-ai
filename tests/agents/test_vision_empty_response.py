"""Regression: une reponse vide du modele de vision n'est jamais un succes."""

from agents.vision.vision_agent import VisionAgent
from apps.backend.pieces_jointes import DepotPiecesJointes

PNG = b"\x89PNG\r\n\x1a\n" + b"vision-empty-response-test"


class ProviderVide:
    async def is_available(self):
        return True

    async def generate(self, prompt, system_prompt=None, images=None):
        return "   "


async def test_reponse_vide_du_modele_est_un_warning():
    depot = DepotPiecesJointes()
    piece = depot.deposer("chantier.png", PNG)
    agent = VisionAgent(provider=ProviderVide(), pieces_jointes=depot)

    reponse = await agent.run(
        "Que vois-tu ?",
        context={"attachments": [piece.identifiant]},
    )

    assert reponse["status"] == "warning"
    assert reponse["response"].strip()
    assert "reponse vide" in reponse["response"].lower()
    assert reponse["images_analysees"] == ["chantier.png"]
