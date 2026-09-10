"""Le moteur de risque : classification et scenarios, tous deterministes.

Les quatre cas de la mission (§20, TEST D) sont testes explicitement : le
moteur doit distinguer une faible volatilite d'une forte, un fort repli, et
une concentration — jamais un seul niveau qui les confond tous.
"""
import pytest

from core.finance import risk


class TestClasserVolatilite:
    def test_faible(self):
        assert risk.classer_volatilite(0.01) is risk.NiveauRisque.FAIBLE

    def test_modere(self):
        assert risk.classer_volatilite(0.03) is risk.NiveauRisque.MODERE

    def test_eleve(self):
        assert risk.classer_volatilite(0.07) is risk.NiveauRisque.ELEVE

    def test_extreme(self):
        assert risk.classer_volatilite(0.20) is risk.NiveauRisque.EXTREME

    def test_none_est_inconnu_jamais_faible(self):
        assert risk.classer_volatilite(None) is risk.NiveauRisque.INCONNU


class TestClasserDrawdown:
    def test_faible(self):
        assert risk.classer_drawdown(-0.05) is risk.NiveauRisque.FAIBLE

    def test_extreme(self):
        assert risk.classer_drawdown(-0.60) is risk.NiveauRisque.EXTREME

    def test_none_est_inconnu(self):
        assert risk.classer_drawdown(None) is risk.NiveauRisque.INCONNU


class TestConcentration:
    def test_un_seul_actif_est_extreme(self):
        assert risk.classer_concentration({"bitcoin": 1.0}) is risk.NiveauRisque.EXTREME

    def test_quatre_positions_egales_est_faible(self):
        poids = {"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}
        assert risk.indice_concentration(poids) == pytest.approx(0.25)
        assert risk.classer_concentration(poids) is risk.NiveauRisque.FAIBLE

    def test_poids_qui_ne_somment_pas_a_un_est_inconnu(self):
        assert risk.classer_concentration({"a": 0.3, "b": 0.3}) is risk.NiveauRisque.INCONNU

    def test_portefeuille_vide_est_inconnu(self):
        assert risk.classer_concentration({}) is risk.NiveauRisque.INCONNU


class TestPire:
    def test_le_plus_severe_gagne(self):
        resultat = risk._pire(risk.NiveauRisque.FAIBLE, risk.NiveauRisque.EXTREME, risk.NiveauRisque.MODERE)
        assert resultat is risk.NiveauRisque.EXTREME

    def test_tout_inconnu_reste_inconnu(self):
        assert risk._pire(risk.NiveauRisque.INCONNU, risk.NiveauRisque.INCONNU) is risk.NiveauRisque.INCONNU

    def test_inconnu_ignore_si_un_autre_est_connu(self):
        # Un facteur non mesure ne doit jamais masquer un facteur mesure et
        # dangereux — INCONNU ne l'emporte jamais sur un niveau reel.
        resultat = risk._pire(risk.NiveauRisque.INCONNU, risk.NiveauRisque.ELEVE)
        assert resultat is risk.NiveauRisque.ELEVE


class TestTaillePosition:
    def test_formule_standard(self):
        # Risque max 1% de 10000 = 100. Distance stop = 5 (105 -> 100).
        # Taille = 100 / 5 = 20 unites.
        taille = risk.taille_position(capital=10000, risque_max_fraction=0.01,
                                       prix_entree=105, prix_stop=100)
        assert taille == pytest.approx(20.0)

    def test_prix_egaux_est_none(self):
        assert risk.taille_position(10000, 0.01, 100, 100) is None

    def test_capital_negatif_est_none(self):
        assert risk.taille_position(-10000, 0.01, 105, 100) is None


class TestScenarioStopLoss:
    def test_stop_en_dessous_du_prix(self):
        # 2x l'ecart-type de 5% sous le prix d'entree.
        stop = risk.scenario_stop_loss(prix_entree=100.0, volatilite=0.05, multiplicateur=2.0)
        assert stop == pytest.approx(90.0)

    def test_sans_volatilite_est_none(self):
        assert risk.scenario_stop_loss(100.0, None) is None


class TestAnalyser:
    def test_faible_volatilite_faible_drawdown(self):
        """TEST D (mission §20) : cas faible."""
        resultat = risk.analyser("bitcoin", volatilite=0.01, drawdown_maximum=-0.03)
        assert resultat.niveau_global is risk.NiveauRisque.FAIBLE

    def test_forte_volatilite(self):
        """TEST D : cas eleve."""
        resultat = risk.analyser("bitcoin", volatilite=0.15, drawdown_maximum=-0.03)
        assert resultat.niveau_global is risk.NiveauRisque.EXTREME

    def test_fort_repli(self):
        """TEST D : gros drawdown."""
        resultat = risk.analyser("bitcoin", volatilite=0.01, drawdown_maximum=-0.55)
        assert resultat.niveau_global is risk.NiveauRisque.EXTREME

    def test_portefeuille_concentre(self):
        """TEST D : concentration."""
        resultat = risk.analyser(
            "bitcoin", volatilite=0.01, drawdown_maximum=-0.02,
            poids_portefeuille={"bitcoin": 1.0},
        )
        assert resultat.niveau_global is risk.NiveauRisque.EXTREME

    def test_les_quatre_cas_sont_distincts(self):
        """Le moteur ne rend jamais le meme niveau pour des situations differentes."""
        faible = risk.analyser("a", volatilite=0.01, drawdown_maximum=-0.02)
        eleve_vol = risk.analyser("b", volatilite=0.15, drawdown_maximum=-0.02)
        gros_drawdown = risk.analyser("c", volatilite=0.01, drawdown_maximum=-0.55)
        concentre = risk.analyser("d", volatilite=0.01, drawdown_maximum=-0.02,
                                   poids_portefeuille={"x": 1.0})
        assert faible.niveau_global is risk.NiveauRisque.FAIBLE
        assert eleve_vol.niveau_global is not faible.niveau_global
        assert gros_drawdown.niveau_global is not faible.niveau_global
        assert concentre.niveau_global is not faible.niveau_global

    def test_stop_et_taille_calcules_quand_le_contexte_existe(self):
        resultat = risk.analyser(
            "bitcoin", volatilite=0.05, drawdown_maximum=-0.02,
            prix_actuel=100.0, capital=10000.0, risque_max_fraction=0.01,
        )
        assert resultat.stop_loss_suggere == pytest.approx(90.0)
        assert resultat.taille_position_suggeree is not None

    def test_to_dict_a_toutes_les_cles(self):
        resultat = risk.analyser("bitcoin", volatilite=0.01, drawdown_maximum=-0.02)
        d = resultat.to_dict()
        for cle in ("actif", "niveau_volatilite", "niveau_drawdown", "niveau_concentration",
                    "niveau_global", "stop_loss_suggere", "taille_position_suggeree"):
            assert cle in d
