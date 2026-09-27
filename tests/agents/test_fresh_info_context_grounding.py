import pytest

from agents.fresh_info.fresh_info_agent import FreshInfoAgent


class MemoryPoison:
    def get_recent_history(self, session_id, limit=8):
        return [
            {"role": "user", "content": "Parle-moi de Brive et Colomiers en rugby."},
        ]


class Provider:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if "Nouvelle question" in prompt:
            return "Qui sont les buteurs du match Angleterre Espagne ?"
        return "Les sources ne répondent pas à la question."


@pytest.mark.asyncio
async def test_historique_fourni_par_interface_est_prioritaire_sur_memoire_stale():
    provider = Provider()
    agent = FreshInfoAgent(provider=provider, memory=MemoryPoison())
    history = [
        {"role": "user", "content": "Qui a gagné entre Angleterre et Espagne ?"},
        {"role": "assistant", "content": "L'Espagne a gagné 3-2."},
        {"role": "user", "content": "Qui est l'homme du match ?"},
    ]

    question = await agent._reformuler_si_ellipse(
        "Qui sont les buteurs ?",
        {"session_id": "match", "history": history},
    )

    assert question == "Qui sont les buteurs du match Angleterre Espagne ?"
    assert "Angleterre et Espagne" in provider.prompts[0]
    assert "Brive" not in provider.prompts[0]


@pytest.mark.asyncio
async def test_historique_autoritatif_vide_ne_relit_jamais_la_memoire_serveur():
    provider = Provider()

    class MemoryInterdite:
        def get_recent_history(self, session_id, limit=8):
            raise AssertionError("un fil autoritatif vide ne doit pas relire la memoire")

    agent = FreshInfoAgent(provider=provider, memory=MemoryInterdite())
    question = await agent._reformuler_si_ellipse(
        "Quel temps fait-il aujourd'hui ?",
        {"session_id": "nouveau-fil", "history": [], "history_authoritative": True},
    )

    assert question == "Quel temps fait-il aujourd'hui ?"
    assert provider.prompts == []


@pytest.mark.asyncio
async def test_sans_historique_interface_relit_plusieurs_tours_de_session():
    provider = Provider()

    class Memory:
        def get_recent_history(self, session_id, limit=8):
            assert limit == 8
            return [
                {"role": "user", "content": "Qui a gagné entre Angleterre et Espagne ?"},
                {"role": "assistant", "content": "L'Espagne a gagné."},
            ]

    agent = FreshInfoAgent(provider=provider, memory=Memory())
    await agent._reformuler_si_ellipse("Qui sont les buteurs ?", {"session_id": "match"})
    assert "Angleterre et Espagne" in provider.prompts[0]


def test_synthese_interdit_de_changer_evenement_pour_coller_aux_sources():
    from agents.fresh_info.fresh_info_agent import GABARIT_SYNTHESE

    assert "HORS SUJET" in GABARIT_SYNTHESE
    assert "Ne change jamais le sujet" in GABARIT_SYNTHESE
