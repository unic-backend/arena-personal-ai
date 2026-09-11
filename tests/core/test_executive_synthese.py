"""Detection de desaccord et synthese — jamais moyennee (mission §8/§9/§30/
§31)."""
import pytest

from core.executive.contrat import AnalyseSpecialiste, NatureDuPoint, PointDeSynthese, Position
from core.executive.synthese import (
    detecter_desaccords,
    synthetiser,
    verifier_coherence_chiffree,
)
from core.models.base import ModelProvider


class FauxProvider(ModelProvider):
    def __init__(self, reponse="Recommandation de synthese.", leve=False):
        self.reponse = reponse
        self.leve = leve
        self.prompts_recus = []

    async def generate(self, prompt, system_prompt=None):
        self.prompts_recus.append(prompt)
        if self.leve:
            raise RuntimeError("modele indisponible")
        return self.reponse

    async def is_available(self):
        return True


def _analyse(role, position, confiance="MOYENNE", **kwargs):
    return AnalyseSpecialiste(role=role, domaine=role, position=position, confiance=confiance, **kwargs)


class TestDetecterDesaccords:
    def test_favorable_contre_defavorable_est_un_desaccord(self):
        analyses = [_analyse("finance", Position.FAVORABLE), _analyse("risque", Position.DEFAVORABLE)]
        desaccords = detecter_desaccords(analyses)
        assert len(desaccords) == 1
        assert {desaccords[0].role_a, desaccords[0].role_b} == {"finance", "risque"}

    def test_conditionnel_n_est_pas_un_desaccord_avec_favorable(self):
        analyses = [_analyse("finance", Position.FAVORABLE), _analyse("operations", Position.CONDITIONNEL)]
        assert detecter_desaccords(analyses) == []

    def test_role_indisponible_jamais_compare(self):
        analyses = [_analyse("finance", Position.FAVORABLE),
                    _analyse("risque", Position.INDISPONIBLE, erreur="panne")]
        assert detecter_desaccords(analyses) == []

    def test_aucun_role_aucun_desaccord(self):
        assert detecter_desaccords([]) == []


class TestVerifierCoherenceChiffree:
    def test_pourcentage_calcule_est_coherent(self):
        analyses = [_analyse("finance", Position.FAVORABLE, preuves=["marge=100 (25.0%)"])]
        assert verifier_coherence_chiffree("La marge est de 25.0% environ.", analyses) is None

    def test_pourcentage_invente_est_signale(self):
        analyses = [_analyse("finance", Position.FAVORABLE, preuves=["marge=100 (25.0%)"])]
        avertissement = verifier_coherence_chiffree("La marge est de 40.0%, excellente.", analyses)
        assert avertissement is not None
        assert "40.0" in avertissement

    def test_aucun_pourcentage_cite_rien_a_verifier(self):
        assert verifier_coherence_chiffree("Reponse sans chiffre.", []) is None


@pytest.mark.asyncio
class TestSynthetiser:
    async def test_aucune_analyse_rend_message_explicite(self):
        decision = await synthetiser("bonjour", [], FauxProvider())
        assert decision.simple
        assert "Aucun role" in decision.reponse

    async def test_desaccord_preserve_dans_la_decision(self):
        analyses = [_analyse("finance", Position.FAVORABLE, actions_recommandees=["accepter"]),
                    _analyse("risque", Position.DEFAVORABLE, risques=["fournisseur unique"])]
        decision = await synthetiser("accepter ce projet ?", analyses, FauxProvider())
        assert len(decision.desaccords) == 1
        assert decision.roles_consultes == ["finance", "risque"]
        assert "fournisseur unique" in decision.risques

    async def test_confiance_globale_prend_le_pire(self):
        analyses = [_analyse("finance", Position.FAVORABLE, confiance="ELEVEE"),
                    _analyse("risque", Position.NEUTRE, confiance="FAIBLE")]
        decision = await synthetiser("x", analyses, FauxProvider())
        assert decision.confiance == "FAIBLE"

    async def test_modele_indisponible_replie_sur_les_constats_bruts(self):
        analyses = [_analyse("finance", Position.FAVORABLE,
                              constats=[PointDeSynthese(texte="marge 25%", nature=NatureDuPoint.CALCUL)])]
        decision = await synthetiser("x", analyses, FauxProvider(leve=True))
        assert "marge 25%" in decision.reponse
        # Le repli EST la recommandation ici : jamais une phrase inventee a
        # la place d'un vrai constat.
        assert "marge 25%" in (decision.recommandation or "")

    async def test_role_indisponible_n_empeche_pas_la_synthese(self):
        """§28 : un role en panne ne bloque pas les autres."""
        analyses = [_analyse("finance", Position.FAVORABLE),
                    _analyse("risque", Position.INDISPONIBLE, erreur="delai depasse")]
        decision = await synthetiser("x", analyses, FauxProvider())
        assert decision.reponse == "Recommandation de synthese."
        assert decision.roles_consultes == ["finance", "risque"]
