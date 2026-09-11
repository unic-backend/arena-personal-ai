"""Le contrat structure des roles executifs (mission §29)."""
from core.executive.contrat import (
    AnalyseSpecialiste,
    DecisionExecutive,
    Desaccord,
    NatureDuPoint,
    PointDeSynthese,
    Position,
)


class TestAnalyseSpecialiste:
    def test_disponible_est_vrai_par_defaut(self):
        analyse = AnalyseSpecialiste(role="finance", domaine="Finance", position=Position.FAVORABLE)
        assert analyse.disponible is True

    def test_disponible_est_faux_si_erreur(self):
        analyse = AnalyseSpecialiste(
            role="finance", domaine="Finance", position=Position.INDISPONIBLE, erreur="panne",
        )
        assert analyse.disponible is False

    def test_to_dict_cles_anglaises(self):
        analyse = AnalyseSpecialiste(
            role="finance", domaine="Finance d'affaires", position=Position.FAVORABLE,
            constats=[PointDeSynthese(texte="marge 20%", nature=NatureDuPoint.CALCUL)],
            preuves=["revenu=100"], hypotheses=["h1"], risques=["r1"],
            confiance="ELEVEE", actions_recommandees=["accepter"], inconnues=["i1"],
        )
        d = analyse.to_dict()
        assert d["role"] == "finance"
        assert d["position"] == "FAVORABLE"
        assert d["findings"] == [{"text": "marge 20%", "nature": "CALCULATION"}]
        assert d["evidence"] == ["revenu=100"]
        assert d["assumptions"] == ["h1"]
        assert d["risks"] == ["r1"]
        assert d["confidence"] == "ELEVEE"
        assert d["recommended_actions"] == ["accepter"]
        assert d["unknowns"] == ["i1"]
        assert d["error"] is None


class TestDesaccord:
    def test_to_dict(self):
        d = Desaccord(role_a="finance", position_a=Position.FAVORABLE,
                      role_b="risque", position_b=Position.DEFAVORABLE, remarque="oppose")
        rendu = d.to_dict()
        assert rendu["position_a"] == "FAVORABLE"
        assert rendu["position_b"] == "UNFAVORABLE"
        assert rendu["note"] == "oppose"


class TestDecisionExecutive:
    def test_simple_reste_courte(self):
        decision = DecisionExecutive(question="bonjour", simple=True, reponse="Bonjour !")
        d = decision.to_dict()
        assert d["simple"] is True
        assert d["response"] == "Bonjour !"
        assert d["specialist_analyses"] == []

    def test_decision_complete(self):
        analyse = AnalyseSpecialiste(role="finance", domaine="Finance", position=Position.FAVORABLE)
        decision = DecisionExecutive(
            question="accepter ce chantier ?", simple=False, reponse="Oui, sous conditions.",
            recommandation="Accepter", pourquoi="marge suffisante",
            roles_consultes=["finance"], analyses=[analyse],
        )
        d = decision.to_dict()
        assert d["recommendation"] == "Accepter"
        assert d["specialists_consulted"] == ["finance"]
        assert len(d["specialist_analyses"]) == 1
        assert d["specialist_analyses"][0]["role"] == "finance"
