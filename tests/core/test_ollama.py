"""Fournisseur Ollama : exige le service local, donc marqué `integration`."""
import pytest


@pytest.mark.integration
async def test_le_service_repond(ollama_en_ligne):
    assert await ollama_en_ligne.is_available() is True


@pytest.mark.integration
async def test_une_generation_renvoie_du_texte(ollama_en_ligne):
    reponse = await ollama_en_ligne.generate(
        prompt="Dis 'ARENA est operationnel' en une phrase courte.",
        system_prompt="Tu es l'assistant de test ARENA.",
    )

    assert reponse.strip() != ""
    assert "<think>" not in reponse


@pytest.mark.integration
async def test_le_streaming_produit_des_jetons(ollama_en_ligne):
    jetons = [j async for j in ollama_en_ligne.generate_stream(prompt="Compte jusqu'a trois.")]

    assert len(jetons) > 0
    assert "".join(jetons).strip() != ""
