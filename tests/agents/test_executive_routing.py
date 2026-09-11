"""Aiguillage vers EXECUTIVE : le controle deterministe, sa collision avec la
date et la finance, et le repli hors-ligne — meme protocole que
`tests/agents/test_finance_routing.py` (mission ARENA x OPENEXECUTIVE, DEC-0086).
"""
import pytest

from agents.orchestrator.orchestrator_agent import OrchestratorAgent


class TestDemandeExecutiveDeterministe:
    @pytest.mark.parametrize("phrase", [
        "devrions-nous accepter ce chantier ?",
        "faut-il accepter ce contrat avec ce fournisseur ?",
        "donne-moi une evaluation executive de la situation",
        "quelle decision d'investissement devrions-nous prendre ?",
        "prepare-moi un brief executif pour la reunion",
        "should we accept this project and under what conditions",
    ])
    def test_locutions_de_decision_declenchent_executive(self, phrase):
        assert OrchestratorAgent.demande_executive(phrase) is True

    @pytest.mark.parametrize("phrase", [
        "accepte mon devis",              # "accepter" seul, hors decision
        "chiffre-moi 18 parois de BA13",  # metier ordinaire
        "corrige ce bug dans le code",    # sans rapport
        "",
    ])
    def test_pas_de_faux_positif(self, phrase):
        assert OrchestratorAgent.demande_executive(phrase) is False


class TestAnalyzeIntentExecutive:
    @pytest.mark.asyncio
    async def test_decision_avec_aujourd_hui_va_a_executive_pas_fresh_info(self, provider_factory):
        agent = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)
        intention = await agent.analyze_intent(
            "Devrions-nous accepter ce chantier aujourd'hui vu le risque fournisseur ?")
        assert intention == "EXECUTIVE"

    @pytest.mark.asyncio
    async def test_analyse_financiere_reste_finance_pas_executive(self, provider_factory):
        """Une question de marche financier (crypto) ne doit jamais etre
        detournee vers l'Executive Intelligence, qui ne sait pas l'analyser."""
        agent = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)
        intention = await agent.analyze_intent("analyse le bitcoin aujourd'hui")
        assert intention == "FINANCE"

    @pytest.mark.asyncio
    async def test_le_modele_peut_aussi_classer_executive(self, provider_factory):
        agent = OrchestratorAgent(provider=provider_factory("EXECUTIVE"), memory=None)
        intention = await agent.analyze_intent("que penses-tu de notre situation financiere globale")
        assert intention == "EXECUTIVE"


class TestRepliHorsLigne:
    def test_classement_par_mots_cles_sans_instance(self):
        assert OrchestratorAgent._classer_par_mots_cles(
            None, "devrions-nous accepter ce contrat ?") == "EXECUTIVE"

    def test_repli_ne_capte_pas_le_metier(self):
        assert OrchestratorAgent._classer_par_mots_cles(None, "chiffre-moi 18 parois de BA13") != "EXECUTIVE"

    def test_repli_ne_capte_pas_le_code(self):
        assert OrchestratorAgent._classer_par_mots_cles(None, "corrige ce bug") != "EXECUTIVE"
