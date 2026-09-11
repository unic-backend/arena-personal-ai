"""Classification de risque d'affaires — deterministe (mission §13/§27)."""
from core.executive.risque_affaires import (
    analyser,
    classer_concentration_client,
    classer_dependance_fournisseur,
    classer_exposition_tresorerie,
    classer_risque_delai,
    pire,
)
from core.finance.risk import NiveauRisque


class TestClasserDependanceFournisseur:
    def test_faible(self):
        assert classer_dependance_fournisseur(0.1) == NiveauRisque.FAIBLE

    def test_extreme(self):
        assert classer_dependance_fournisseur(0.9) == NiveauRisque.EXTREME

    def test_inconnu_si_absent(self):
        assert classer_dependance_fournisseur(None) == NiveauRisque.INCONNU


class TestClasserRisqueDelai:
    def test_marge_negative_est_extreme(self):
        assert classer_risque_delai(-5, 14) == NiveauRisque.EXTREME

    def test_marge_confortable_est_faible(self):
        assert classer_risque_delai(20, 14) == NiveauRisque.FAIBLE

    def test_inconnu_sans_duree(self):
        assert classer_risque_delai(5, None) == NiveauRisque.INCONNU
        assert classer_risque_delai(5, 0) == NiveauRisque.INCONNU


class TestClasserExpositionTresorerie:
    def test_ratio_sous_un_est_eleve(self):
        assert classer_exposition_tresorerie(900, 1000) == NiveauRisque.ELEVE

    def test_ratio_superieur_a_un_est_extreme(self):
        assert classer_exposition_tresorerie(1500, 1000) == NiveauRisque.EXTREME

    def test_tresorerie_nulle_avec_depense_est_extreme(self):
        assert classer_exposition_tresorerie(100, 0) == NiveauRisque.EXTREME

    def test_tresorerie_nulle_sans_depense_est_faible(self):
        assert classer_exposition_tresorerie(0, 0) == NiveauRisque.FAIBLE


class TestClasserConcentrationClient:
    def test_faible(self):
        assert classer_concentration_client(0.1) == NiveauRisque.FAIBLE

    def test_extreme(self):
        assert classer_concentration_client(0.7) == NiveauRisque.EXTREME


class TestPire:
    def test_le_pire_l_emporte(self):
        assert pire(NiveauRisque.FAIBLE, NiveauRisque.EXTREME, NiveauRisque.MODERE) == NiveauRisque.EXTREME

    def test_inconnu_n_emporte_jamais_sur_un_niveau_mesure(self):
        assert pire(NiveauRisque.INCONNU, NiveauRisque.FAIBLE) == NiveauRisque.FAIBLE

    def test_tout_inconnu_reste_inconnu(self):
        assert pire(NiveauRisque.INCONNU, NiveauRisque.INCONNU) == NiveauRisque.INCONNU

    def test_aucun_argument(self):
        assert pire() == NiveauRisque.INCONNU


class TestAnalyser:
    def test_combine_les_facteurs_fournis(self):
        r = analyser(dependance_fournisseur=0.9, marge_jours=-2, duree_totale_jours=14)
        assert r.niveau_global == NiveauRisque.EXTREME
        assert r.facteurs["supplier_dependency"] == NiveauRisque.EXTREME
        assert r.facteurs["deadline_risk"] == NiveauRisque.EXTREME

    def test_aucun_facteur_fourni_est_inconnu(self):
        r = analyser()
        assert r.niveau_global == NiveauRisque.INCONNU
        assert all(v == NiveauRisque.INCONNU for v in r.facteurs.values())

    def test_to_dict(self):
        r = analyser(dependance_fournisseur=0.1)
        d = r.to_dict()
        assert d["overall_level"] == "LOW"
        assert d["factors"]["supplier_dependency"] == "LOW"
        assert d["factors"]["deadline_risk"] == "UNKNOWN"
