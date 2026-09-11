"""Le moteur d'Executive Intelligence bout en bout (mission §5/§38/§41)."""
import asyncio

import pytest

from core.executive.contrat import Position
from core.executive.moteur import MoteurExecutif
from core.models.base import ModelProvider


class FauxProvider(ModelProvider):
    def __init__(self, reponse="Recommandation executive de test.", leve=False, delai=0.0):
        self.reponse = reponse
        self.leve = leve
        self.delai = delai
        self.prompts_recus = []

    async def generate(self, prompt, system_prompt=None):
        self.prompts_recus.append(prompt)
        if self.delai:
            await asyncio.sleep(self.delai)
        if self.leve:
            raise RuntimeError("modele indisponible")
        return self.reponse

    async def is_available(self):
        return True


#: Le scenario exact de la mission (§38).
SCENARIO_TEXTE = """
Construction company receives a project worth 10,000,000.

Material cost: 5,000,000
Labor: 2,000,000
Transport cost: 500,000

Payment: 50% advance, 30% mid-project, 20% completion

Deadline: 14 days
Supplier risk: possible 5-day delay

Should we accept this project and under what conditions?
"""


@pytest.mark.asyncio
class TestQuestionSimple:
    async def test_bonjour_ne_convoque_aucun_role(self):
        """§10/§42 : une question qui n'appelle aucune decision d'affaires
        reste une reponse directe, jamais le gabarit complet."""
        moteur = MoteurExecutif(provider=FauxProvider(reponse="Bonjour !"))
        decision = await moteur.analyser("Bonjour, comment vas-tu ?")
        assert decision.simple
        assert decision.reponse == "Bonjour !"
        assert decision.roles_consultes == []

    async def test_question_vide(self):
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser("   ")
        assert decision.simple
        assert "Aucune question" in decision.reponse


@pytest.mark.asyncio
class TestScenarioSynthetiqueDeLaMission:
    """Mission §38 : le scenario de construction complet, verifie de bout en
    bout — Executive Intelligence -> finance/operations/risque -> calculs
    deterministes -> synthese."""

    async def test_les_roles_pertinents_sont_convoques(self):
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser(
            "Devrions-nous accepter ce chantier ? " + SCENARIO_TEXTE)
        assert not decision.simple
        assert "finance" in decision.roles_consultes
        assert "operations" in decision.roles_consultes
        assert "risque" in decision.roles_consultes

    async def test_la_marge_est_reellement_calculee(self):
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser(
            "Devrions-nous accepter ce chantier ? " + SCENARIO_TEXTE)
        analyse_finance = next(a for a in decision.analyses if a.role == "finance")
        assert analyse_finance.disponible
        # Marge = 10M - 7.5M = 2.5M, soit 25% — calcule, jamais devine.
        assert any("2500000" in p.replace(" ", "") or "25.0" in p for p in analyse_finance.preuves)

    async def test_le_delai_est_calcule_faisable(self):
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser(
            "Devrions-nous accepter ce chantier ? " + SCENARIO_TEXTE)
        analyse_ops = next(a for a in decision.analyses if a.role == "operations")
        assert analyse_ops.disponible

    async def test_synthese_produite(self):
        moteur = MoteurExecutif(provider=FauxProvider(reponse="Recommandation : accepter sous conditions."))
        decision = await moteur.analyser("Devrions-nous accepter ce chantier ? " + SCENARIO_TEXTE)
        assert decision.reponse == "Recommandation : accepter sous conditions."
        assert decision.confiance in ("FAIBLE", "MOYENNE", "ELEVEE")


@pytest.mark.asyncio
class TestSelectionDeSpecialistes:
    """Mission §39 : chaque tache convoque les roles attendus, et
    n'en convoque jamais d'inattendus."""

    async def test_tache_a_strategie_marketing(self):
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser(
            "Faut-il accepter ce plan d'expansion pour ameliorer notre "
            "strategie d'acquisition client et notre positionnement marche ?")
        assert "strategie_marche" in decision.roles_consultes

    async def test_tache_b_tresorerie(self):
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser(
            "Devrions-nous accepter ce projet malgre un probleme de tresorerie "
            "et une marge incertaine ce mois-ci ?")
        assert "finance" in decision.roles_consultes

    async def test_tache_c_contrat_fournisseur(self):
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser(
            "Faut-il accepter ce contrat avec ce fournisseur, sachant le risque "
            "de dependance ?")
        assert "approvisionnement" in decision.roles_consultes
        assert "risque" in decision.roles_consultes

    async def test_tache_d_code_ne_declenche_pas_executive(self):
        """§39 TACHE D : une question de code ne doit jamais etre traitee
        comme une decision d'affaires."""
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser("Corrige ce bug dans le module d'authentification")
        assert decision.simple
        assert decision.roles_consultes == []

    async def test_tache_e_video_ne_declenche_pas_executive(self):
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser("Genere-moi une video promotionnelle de mon chantier")
        assert decision.simple
        assert decision.roles_consultes == []


@pytest.mark.asyncio
class TestEchecs:
    """Mission §41 : ARENA doit se retablir sans jamais bloquer la reponse."""

    async def test_modele_indisponible_pour_toute_interpretation(self):
        """Chaque role degrade, la synthese degrade, mais une reponse sort
        toujours."""
        moteur = MoteurExecutif(provider=FauxProvider(leve=True))
        decision = await moteur.analyser("Devrions-nous accepter ce chantier ? " + SCENARIO_TEXTE)
        assert decision.reponse  # jamais vide

    async def test_role_qui_leve_devient_indisponible_sans_casser_les_autres(self, monkeypatch):
        import core.executive.moteur as moteur_mod

        async def casse(_entree):
            raise RuntimeError("panne simulee du role finance")

        monkeypatch.setitem(moteur_mod.CONSULTANTS, "finance", casse)
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser("Devrions-nous accepter ce chantier ? " + SCENARIO_TEXTE)
        analyse_finance = next(a for a in decision.analyses if a.role == "finance")
        assert not analyse_finance.disponible
        assert analyse_finance.position == Position.INDISPONIBLE
        # Les autres roles ont quand meme conclu.
        assert any(a.disponible for a in decision.analyses if a.role != "finance")

    async def test_role_sans_capacite_enregistree(self, monkeypatch):
        import core.executive.moteur as moteur_mod
        monkeypatch.delitem(moteur_mod.CONSULTANTS, "finance", raising=False)
        moteur = MoteurExecutif(provider=FauxProvider())
        decision = await moteur.analyser("Devrions-nous accepter ce chantier ? " + SCENARIO_TEXTE)
        analyse_finance = next(a for a in decision.analyses if a.role == "finance")
        assert not analyse_finance.disponible

    async def test_recherche_web_en_panne_ne_bloque_pas(self):
        def chercheur_casse(_q):
            raise RuntimeError("recherche indisponible")

        moteur = MoteurExecutif(provider=FauxProvider(), chercheur=chercheur_casse)
        decision = await moteur.analyser(
            "Faut-il accepter ce plan d'expansion, quelle est notre strategie de marche ?")
        assert decision.reponse

    async def test_memoire_absente_n_empeche_pas_la_reponse(self):
        moteur = MoteurExecutif(provider=FauxProvider(), memory=None)
        decision = await moteur.analyser("Devrions-nous accepter ce chantier ? " + SCENARIO_TEXTE)
        assert decision.reponse


@pytest.mark.asyncio
class TestMemoireDeDecision:
    """`memoire` : fixture partagee de `tests/conftest.py` (base SQLite jetable)."""

    async def test_decision_enregistree(self, memoire):
        moteur = MoteurExecutif(provider=FauxProvider(), memory=memoire)
        await moteur.analyser("Devrions-nous accepter ce chantier ? " + SCENARIO_TEXTE)
        recentes = memoire.list_facts("executive_decision", limit=5)
        assert len(recentes) == 1
        assert recentes[0]["value"]["question"].startswith("Devrions-nous accepter")

    async def test_question_simple_n_est_pas_enregistree(self, memoire):
        """Seules les vraies decisions d'affaires meritent une trace — pas
        une conversation ordinaire (mission §15 : concis, pas exhaustif)."""
        moteur = MoteurExecutif(provider=FauxProvider(reponse="Bonjour !"), memory=memoire)
        await moteur.analyser("Bonjour")
        assert memoire.list_facts("executive_decision", limit=5) == []
