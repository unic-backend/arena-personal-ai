"""VisionAgent : une image se decrit, elle ne s'invente jamais (DEC-0019).

Rien n'appelle Ollama : le fournisseur est le double du socle
(`tests/conftest.py`), le depot de pieces jointes est reel mais jetable.
"""
import httpx
import pytest

from agents.vision.vision_agent import QUESTION_PAR_DEFAUT, VisionAgent
from apps.backend.pieces_jointes import DepotPiecesJointes

OCTETS_IMAGE = b"\x89PNG\r\n\x1a\n" + b"faux-png-mais-suffit-pour-le-test"


@pytest.fixture
def depot():
    return DepotPiecesJointes()


class TestSansImage:
    async def test_sans_piece_jointe_l_agent_le_dit(self, fake_provider):
        agent = VisionAgent(provider=fake_provider, pieces_jointes=DepotPiecesJointes())

        reponse = await agent.run("Que vois-tu ?", context={"attachments": []})

        assert reponse["status"] == "error"
        assert "aucune image" in reponse["response"].lower()
        assert fake_provider.appels == []

    async def test_une_piece_jointe_texte_ne_compte_pas_comme_image(self, fake_provider, depot):
        piece = depot.deposer("devis.txt", b"486 m2 de BA13")
        agent = VisionAgent(provider=fake_provider, pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "error"
        assert fake_provider.appels == []

    async def test_sans_depot_de_pieces_jointes_rien_ne_part(self, fake_provider):
        agent = VisionAgent(provider=fake_provider, pieces_jointes=None)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": ["peu-importe"]})

        assert reponse["status"] == "error"
        assert fake_provider.appels == []

    async def test_un_identifiant_inconnu_est_ignore_pas_invente(self, fake_provider, depot):
        agent = VisionAgent(provider=fake_provider, pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": ["jamais-depose"]})

        assert reponse["status"] == "error"
        assert fake_provider.appels == []


class TestAvecImage:
    async def test_l_image_part_vers_le_modele(self, provider_factory, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Un mur en BA13, non fini.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "success"
        assert reponse["response"] == "Un mur en BA13, non fini."
        assert provider.appels[0]["images"] == [piece.image_base64]
        assert reponse["images_analysees"] == ["chantier.jpg"]

    async def test_la_question_par_defaut_sert_sans_texte(self, provider_factory, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo de chantier.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        await agent.run("", context={"attachments": [piece.identifiant]})

        assert QUESTION_PAR_DEFAUT in provider.appels[0]["prompt"]

    async def test_le_rappel_donnee_accompagne_toujours_le_prompt(self, provider_factory, depot):
        """Une consigne ecrite sur l'image ne doit pas passer pour une consigne
        du proprietaire — meme discipline que pour un document joint."""
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = provider_factory("Une photo de chantier.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert "DONNEE" in provider.appels[0]["prompt"]

    async def test_plusieurs_images_partent_toutes(self, provider_factory, depot):
        piece1 = depot.deposer("avant.jpg", OCTETS_IMAGE)
        piece2 = depot.deposer("apres.jpg", OCTETS_IMAGE)
        provider = provider_factory("Deux photos comparees.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        reponse = await agent.run(
            "Compare ces deux photos.",
            context={"attachments": [piece1.identifiant, piece2.identifiant]})

        assert len(provider.appels[0]["images"]) == 2
        assert reponse["images_analysees"] == ["avant.jpg", "apres.jpg"]

    async def test_une_piece_texte_melangee_a_une_image_est_filtree(self, provider_factory, depot):
        image = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        texte = depot.deposer("devis.txt", b"486 m2")
        provider = provider_factory("Une photo de chantier.")
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        reponse = await agent.run(
            "Que vois-tu ?", context={"attachments": [texte.identifiant, image.identifiant]})

        assert reponse["images_analysees"] == ["chantier.jpg"]
        assert len(provider.appels[0]["images"]) == 1


class TestOllamaIndisponible:
    async def test_ollama_eteint_rend_not_configured(self, depot):
        from tests.conftest import FakeProvider

        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        provider = FakeProvider(disponible=False)
        agent = VisionAgent(provider=provider, pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "warning"
        assert "ollama" in reponse["response"].lower()


class TestModeleAbsent:
    """`OllamaProvider.generate` leve quand le modele de vision n'est pas
    installe — l'agent doit le dire, pas planter."""

    class ProviderQuiRefuse:
        async def is_available(self):
            return True

        async def generate(self, prompt, system_prompt=None, images=None):
            requete = httpx.Request("POST", "http://localhost/api/generate")
            reponse = httpx.Response(404, request=requete, text="model not found")
            raise httpx.HTTPStatusError("404", request=requete, response=reponse)

    async def test_le_modele_absent_est_signale_clairement(self, depot):
        piece = depot.deposer("chantier.jpg", OCTETS_IMAGE)
        agent = VisionAgent(provider=self.ProviderQuiRefuse(), pieces_jointes=depot)

        reponse = await agent.run("Que vois-tu ?", context={"attachments": [piece.identifiant]})

        assert reponse["status"] == "warning"
        assert "qwen3-vl" in reponse["response"]
