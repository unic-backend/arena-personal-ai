"""L'agent Executive Intelligence — un BaseAgent mince (mission ARENA x
OPENEXECUTIVE, DEC-0086)."""
import pytest

from agents.executive.executive_agent import ExecutiveAgent
from core.models.base import ModelProvider


class FauxProvider(ModelProvider):
    async def generate(self, prompt, system_prompt=None):
        return "Recommandation de test."

    async def is_available(self):
        return True


@pytest.mark.asyncio
class TestExecutiveAgent:
    async def test_run_rend_la_forme_standard(self):
        agent = ExecutiveAgent(provider=FauxProvider())
        resultat = await agent.run("Bonjour")
        assert resultat["status"] == "success"
        assert resultat["agent"] == "ExecutiveAgent"
        assert "executive_decision" in resultat
        assert resultat["executive_decision"]["question"] == "Bonjour"

    async def test_aucune_capacite_d_ecriture_appelee(self):
        """Mission §23/§24 : l'agent ne fait jamais qu'une recommandation —
        aucune methode d'action (envoi, paiement, commande) n'existe sur lui."""
        agent = ExecutiveAgent(provider=FauxProvider())
        interdits = ("envoyer", "payer", "commander", "publier", "supprimer", "executer_action")
        for methode in interdits:
            assert not hasattr(agent, methode)

    async def test_construction_par_defaut_utilise_le_vrai_outil_de_recherche(self):
        """Meme outil que FinanceAgent — jamais un second moteur (mission §20)."""
        agent = ExecutiveAgent(provider=FauxProvider())
        assert agent.moteur.chercheur is not None  # adaptateur construit, pas None
