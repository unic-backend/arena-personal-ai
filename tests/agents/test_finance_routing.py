"""Aiguillage vers FINANCE : le controle deterministe, sa collision avec la
date, et le repli hors-ligne — meme protocole que `tests/agents/test_orchestrator.py`.
"""
import pytest

from agents.orchestrator.orchestrator_agent import OrchestratorAgent


class TestDemandeFinanciereDeterministe:
    @pytest.mark.parametrize("phrase", [
        "analyse le bitcoin",
        "analyse bitcoin aujourd'hui",
        "analyses ethereum",
        "quel est le risque de cette position sur le bitcoin",
        "évalue le risque de ce marché crypto",
        "dois-je investir dans le bitcoin",
        "analyse le BTC",  # ticker, frontiere de mot
    ])
    def test_verbe_et_actif_declenchent_finance(self, phrase):
        assert OrchestratorAgent.demande_financiere(phrase) is True

    @pytest.mark.parametrize("phrase", [
        "quel est le cours du bitcoin",          # pas de verbe d'analyse
        "le bitcoin a beaucoup chute cette semaine",  # actif sans verbe
        "analyse ce devis de cloison BA13",       # verbe sans actif financier
        "isole ce mur avant de couler la dalle",  # "isole" ne doit jamais matcher "sol"
        "analyse ce mur isolé avant le chantier",  # verbe PRESENT + "isolé" contient "sol"
        "resous cette equation",                  # sans rapport
        "",
    ])
    def test_pas_de_faux_positif(self, phrase):
        assert OrchestratorAgent.demande_financiere(phrase) is False


class TestAnalyzeIntentFinance:
    """La collision avec `exige_verification` (mots de date/actualite),
    reglee comme celle du courrier le 31/08/2026."""

    @pytest.mark.asyncio
    async def test_analyse_avec_aujourd_hui_va_a_finance_pas_fresh_info(self, provider_factory):
        # "aujourd'hui" est dans FORMULATIONS_COURANTES : sans le controle
        # deterministe, cette phrase partirait en FRESH_INFO.
        agent = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)
        intention = await agent.analyze_intent("analyse le bitcoin aujourd'hui")
        assert intention == "FINANCE"

    @pytest.mark.asyncio
    async def test_simple_question_de_cours_reste_fresh_info(self, provider_factory):
        agent = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)
        intention = await agent.analyze_intent("quel est le cours du bitcoin aujourd'hui")
        assert intention == "FRESH_INFO"

    @pytest.mark.asyncio
    async def test_le_modele_peut_aussi_classer_finance(self, provider_factory):
        # Une formulation trop ouverte pour le controle deterministe
        # (aucun verbe de la liste) : c'est au modele de la reconnaitre.
        agent = OrchestratorAgent(provider=provider_factory("FINANCE"), memory=None)
        intention = await agent.analyze_intent("que penses-tu de la situation du marche crypto")
        assert intention == "FINANCE"


class TestRepliHorsLigne:
    def test_classement_par_mots_cles_sans_instance(self):
        # Meme protocole que le reste du fichier : appelee sans self, la ou
        # aucun modele n'est joignable.
        assert OrchestratorAgent._classer_par_mots_cles(None, "analyse le bitcoin") == "FINANCE"

    def test_repli_ne_capte_pas_le_metier(self):
        assert OrchestratorAgent._classer_par_mots_cles(None, "chiffre-moi 18 parois de BA13") != "FINANCE"


class TestAnalyzeIntentDate:
    """**Le controle existe-t-il, ou est-il branche ?**

    `demande_la_date()` peut etre parfait et ne servir a rien si
    `analyze_intent` ne l'appelle pas. Mesure du 15/09/2026 : en retirant
    l'appel, les tests de la methode restaient tous verts — *« une garde qui
    verifie qu'une piece existe ne verifie pas qu'elle est branchee »*.

    Ces tests-ci passent par `analyze_intent`, et le fournisseur est scripte
    pour repondre `FRESH_INFO` : si le controle de date disparaissait, la
    question partirait au web et l'assertion tomberait.
    """

    @pytest.mark.asyncio
    async def test_la_date_du_jour_va_au_chat_pas_au_web(self, provider_factory):
        agent = OrchestratorAgent(provider=provider_factory("FRESH_INFO"), memory=None)

        intention = await agent.analyze_intent("Aujourd'hui c'est quand")

        assert intention == "CHAT"

    @pytest.mark.asyncio
    async def test_une_vraie_question_de_fraicheur_va_toujours_au_web(
            self, provider_factory):
        """Le controle de date ne doit rien voler a `FRESH_INFO`."""
        agent = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)

        intention = await agent.analyze_intent("quel temps fait-il aujourd’hui")

        assert intention == "FRESH_INFO"
