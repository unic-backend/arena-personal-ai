"""Calcul financier deterministe (mission §13/§14) — le scenario du chantier
de construction de la mission (§38) sert de fil rouge."""
from core.executive.calcul_affaires import (
    ScenarioAffaires,
    calculer_echeancier,
    calculer_marge,
    comparer_scenarios,
    evaluer_faisabilite_delai,
)


class TestCalculerMarge:
    def test_marge_positive(self):
        r = calculer_marge(10_000_000, {"materials": 5_000_000, "labor": 2_000_000, "transport": 500_000})
        assert r.valide
        assert r.cout_total == 7_500_000
        assert r.marge_brute == 2_500_000
        assert round(r.marge_pourcent, 1) == 25.0

    def test_revenu_manquant_refuse(self):
        r = calculer_marge(0, {"materials": 100})
        assert not r.valide
        assert "revenu" in r.raison

    def test_revenu_negatif_refuse(self):
        assert not calculer_marge(-5, {"a": 1}).valide

    def test_aucun_cout_refuse(self):
        r = calculer_marge(1000, {})
        assert not r.valide
        assert "cout" in r.raison

    def test_cout_negatif_refuse(self):
        r = calculer_marge(1000, {"materials": -5})
        assert not r.valide
        assert "negatif" in r.raison

    def test_marge_negative_reste_calculee(self):
        r = calculer_marge(100, {"materials": 200})
        assert r.valide
        assert r.marge_brute == -100


class TestCalculerEcheancier:
    def test_echeancier_valide(self):
        r = calculer_echeancier(10_000_000, [("advance", 50), ("mid-project", 30), ("completion", 20)])
        assert r.valide
        assert len(r.etapes) == 3
        assert r.etapes[0].montant == 5_000_000
        assert r.etapes[1].montant == 3_000_000
        assert r.etapes[2].montant == 2_000_000

    def test_pourcentages_qui_ne_totalisent_pas_100_refuses(self):
        r = calculer_echeancier(1000, [("a", 50), ("b", 30)])
        assert not r.valide
        assert "80" in r.raison

    def test_tolerance_arrondi_acceptee(self):
        r = calculer_echeancier(1000, [("a", 33.3), ("b", 33.3), ("c", 33.4)])
        assert r.valide

    def test_montant_total_manquant_refuse(self):
        assert not calculer_echeancier(0, [("a", 100)]).valide

    def test_aucune_echeance_refusee(self):
        assert not calculer_echeancier(1000, []).valide


class TestFaisabiliteDelai:
    def test_faisable_confortable(self):
        r = evaluer_faisabilite_delai(30, 14, 5)
        assert r.valide
        assert r.faisable
        assert r.marge_jours == 11

    def test_non_faisable(self):
        r = evaluer_faisabilite_delai(14, 14, 5)
        assert r.valide
        assert not r.faisable
        assert r.marge_jours == -5

    def test_delai_disponible_manquant_refuse(self):
        assert not evaluer_faisabilite_delai(0, 5).valide

    def test_duree_estimee_negative_refusee(self):
        assert not evaluer_faisabilite_delai(10, -1).valide

    def test_risque_par_defaut_est_zero(self):
        r = evaluer_faisabilite_delai(10, 5)
        assert r.jours_risque == 0.0
        assert r.marge_jours == 5


class TestComparerScenarios:
    def test_delta_par_rapport_a_la_base(self):
        base = ScenarioAffaires(nom="base", revenu=10_000_000,
                                 couts={"materials": 5_000_000, "labor": 2_000_000, "transport": 500_000})
        variante = ScenarioAffaires(nom="materiaux +10%", revenu=10_000_000,
                                     couts={"materials": 5_500_000, "labor": 2_000_000, "transport": 500_000})
        resultats = comparer_scenarios(base, [variante])
        assert len(resultats) == 1
        assert resultats[0].marge.marge_brute == 2_000_000
        assert resultats[0].delta_marge == -500_000

    def test_scenario_avec_delai(self):
        base = ScenarioAffaires(nom="base", revenu=1000, couts={"a": 500},
                                 jours_disponibles=30, jours_estimes=14)
        variante = ScenarioAffaires(nom="retard", revenu=1000, couts={"a": 500},
                                     jours_disponibles=30, jours_estimes=25)
        resultats = comparer_scenarios(base, [variante])
        assert resultats[0].faisabilite is not None
        assert resultats[0].faisabilite.faisable

    def test_base_invalide_ne_casse_pas_le_delta(self):
        base = ScenarioAffaires(nom="base", revenu=0, couts={})
        variante = ScenarioAffaires(nom="v", revenu=1000, couts={"a": 500})
        resultats = comparer_scenarios(base, [variante])
        assert resultats[0].marge.valide
        assert resultats[0].delta_marge is None
