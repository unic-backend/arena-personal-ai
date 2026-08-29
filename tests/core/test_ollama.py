"""Fournisseur Ollama : exige le service local, donc marqué `integration`.

Deux tests en bas (`TestImages`) restent hors ligne : ils verifient que le
parametre `images` (DEC-0019) construit bien la requete attendue par
`/api/generate`, sans jamais toucher au reseau — le client HTTP est double.
"""
import json

import httpx
import pytest

from core.models.ollama_provider import NUM_CTX_VISION, OllamaProvider


@pytest.mark.integration
async def test_le_service_repond(ollama_en_ligne):
    assert await ollama_en_ligne.is_available() is True


@pytest.mark.integration
async def test_une_generation_renvoie_du_texte(ollama_en_ligne):
    reponse = await ollama_en_ligne.generate(
        prompt="Dis 'Usman est operationnel' en une phrase courte.",
        system_prompt="Tu es l'assistant de test Usman.",
    )

    assert reponse.strip() != ""
    assert "<think>" not in reponse


@pytest.mark.integration
async def test_le_streaming_produit_des_jetons(ollama_en_ligne):
    jetons = [j async for j in ollama_en_ligne.generate_stream(prompt="Compte jusqu'a trois.")]

    assert len(jetons) > 0
    assert "".join(jetons).strip() != ""


class TestImages:
    """`OllamaProvider.generate(images=...)` — la requete, jamais le reseau."""

    @pytest.fixture
    def provider_et_requetes(self, monkeypatch):
        requetes = []

        def repondre(requete: httpx.Request) -> httpx.Response:
            requetes.append(json.loads(requete.content))
            return httpx.Response(200, json={"response": "une scene de chantier"})

        vrai_client = httpx.AsyncClient

        def fabrique(*args, **kw):
            kw["transport"] = httpx.MockTransport(repondre)
            return vrai_client(*args, **kw)

        monkeypatch.setattr(httpx, "AsyncClient", fabrique)
        return OllamaProvider(model_name="qwen3-vl:4b"), requetes

    async def test_les_images_partent_dans_la_requete(self, provider_et_requetes):
        provider, requetes = provider_et_requetes

        await provider.generate(prompt="Que vois-tu ?", images=["YmFzZTY0"])

        assert requetes[0]["images"] == ["YmFzZTY0"]

    async def test_sans_image_le_champ_est_absent(self, provider_et_requetes):
        """Un modele texte ne doit jamais recevoir un champ `images` vide."""
        provider, requetes = provider_et_requetes

        await provider.generate(prompt="Bonjour")

        assert "images" not in requetes[0]

    async def test_une_image_elargit_le_contexte(self, provider_et_requetes):
        """Le budget fixe pour la vitesse en conversation couperait la
        description d'une image avant qu'elle ne commence."""
        provider, requetes = provider_et_requetes

        await provider.generate(prompt="Que vois-tu ?", images=["YmFzZTY0"])

        assert requetes[0]["options"]["num_ctx"] == NUM_CTX_VISION

    async def test_sans_image_le_contexte_reste_celui_de_la_conversation(self, provider_et_requetes):
        provider, requetes = provider_et_requetes

        await provider.generate(prompt="Bonjour")

        assert requetes[0]["options"]["num_ctx"] == 4096

    async def test_la_reponse_est_rendue_normalement(self, provider_et_requetes):
        provider, _ = provider_et_requetes

        reponse = await provider.generate(prompt="Que vois-tu ?", images=["YmFzZTY0"])

        assert reponse == "une scene de chantier"
