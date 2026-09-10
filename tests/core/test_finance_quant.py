"""Le moteur quantitatif : arithmetique pure, verifiee a la main.

Chaque test qui calcule quelque chose verifie le nombre exact, pas juste
« un nombre est rendu » — sinon un bug dans la formule passerait comme un
succes. Chaque fonction a aussi son test « pas assez de donnees » : le
contrat central du module est qu'une valeur non calculable rend `None`,
jamais 0.
"""

import pytest

from core.finance import quant


def _serie(prix: list) -> list:
    """Une serie (horodatage, prix) a partir d'une simple liste de prix —
    l'horodatage n'entre dans aucun calcul de ce module."""
    return [(i * 1000, p) for i, p in enumerate(prix)]


class TestRendements:
    def test_rendements_periode_a_periode(self):
        serie = _serie([100.0, 110.0, 99.0])
        r = quant.rendements(serie)
        assert r == pytest.approx([0.10, -0.10])

    def test_rendement_total(self):
        assert quant.rendement_total(_serie([100.0, 150.0])) == pytest.approx(0.5)

    def test_rendement_total_moins_de_deux_points_est_none(self):
        assert quant.rendement_total(_serie([100.0])) is None
        assert quant.rendement_total([]) is None


class TestVolatilite:
    def test_serie_constante_est_zero(self):
        assert quant.volatilite(_serie([100.0] * 10)) == pytest.approx(0.0)

    def test_deux_prix_donne_un_seul_rendement_donc_none(self):
        # Un seul rendement -> pstdev indefini -> None (pas 0).
        assert quant.volatilite(_serie([100.0, 110.0])) is None

    def test_volatilite_reelle(self):
        # Rendements : +0.02, -0.01/1.02≈-0.00980..., calcules a la main via statistics.
        import statistics
        prix = [100.0, 102.0, 101.0]
        rendements_attendus = [0.02, (101.0 - 102.0) / 102.0]
        assert quant.volatilite(_serie(prix)) == pytest.approx(statistics.pstdev(rendements_attendus))


class TestMoyennesMobiles:
    def test_sma_simple(self):
        assert quant.moyenne_mobile(_serie([1.0, 2.0, 3.0, 4.0]), 2) == pytest.approx(3.5)

    def test_sma_pas_assez_de_points_est_none(self):
        assert quant.moyenne_mobile(_serie([1.0, 2.0]), 5) is None

    def test_ema_amorcee_par_la_sma(self):
        # periode=2 : EMA[0] = SMA(1,2) = 1.5, lissage = 2/3.
        # EMA[1] = 3*(2/3) + 1.5*(1/3) = 2 + 0.5 = 2.5
        prix = [1.0, 2.0, 3.0]
        resultat = quant.moyenne_mobile_exponentielle(_serie(prix), 2)
        assert resultat == pytest.approx(2.5)

    def test_ema_pas_assez_de_points_est_none(self):
        assert quant.moyenne_mobile_exponentielle(_serie([1.0]), 5) is None


class TestMomentum:
    def test_momentum_positif(self):
        prix = [100.0] * 5 + [120.0]  # variation sur les 5 derniers points depuis prix[-1-5]
        assert quant.momentum(_serie(prix), periode=5) == pytest.approx(0.20)

    def test_pas_assez_de_points_est_none(self):
        assert quant.momentum(_serie([100.0, 101.0]), periode=10) is None


class TestRSI:
    def test_pas_assez_de_points_est_none(self):
        assert quant.rsi(_serie([100.0] * 5), periode=14) is None

    def test_hausse_constante_donne_rsi_100(self):
        # Aucune perte jamais -> perte_moyenne == 0 -> RSI = 100 par construction.
        prix = [100.0 + i for i in range(20)]
        assert quant.rsi(_serie(prix), periode=14) == pytest.approx(100.0)

    def test_baisse_constante_donne_rsi_0(self):
        prix = [100.0 - i for i in range(20)]
        assert quant.rsi(_serie(prix), periode=14) == pytest.approx(0.0)


class TestMACD:
    def test_pas_assez_de_points_est_none(self):
        assert quant.macd(_serie([100.0] * 10)) is None

    def test_serie_constante_donne_un_histogramme_nul(self):
        prix = [100.0] * 40
        resultat = quant.macd(_serie(prix))
        assert resultat is not None
        assert resultat["ligne"] == pytest.approx(0.0)
        assert resultat["histogramme"] == pytest.approx(0.0)


class TestBollinger:
    def test_pas_assez_de_points_est_none(self):
        assert quant.bandes_bollinger(_serie([100.0] * 5), periode=20) is None

    def test_serie_constante_bandes_confondues_avec_le_centre(self):
        resultat = quant.bandes_bollinger(_serie([100.0] * 25), periode=20)
        assert resultat["centre"] == pytest.approx(100.0)
        assert resultat["superieure"] == pytest.approx(100.0)
        assert resultat["inferieure"] == pytest.approx(100.0)


class TestSupportResistance:
    def test_support_et_resistance(self):
        resultat = quant.support_resistance(_serie([100.0, 90.0, 110.0, 95.0]), periode=10)
        assert resultat["support"] == pytest.approx(90.0)
        assert resultat["resistance"] == pytest.approx(110.0)

    def test_serie_vide_est_none(self):
        assert quant.support_resistance([]) is None


class TestDrawdownMaximum:
    def test_chute_depuis_un_sommet(self):
        # Sommet a 100, plus bas a 50 -> -50%.
        resultat = quant.drawdown_maximum(_serie([100.0, 100.0, 50.0, 80.0]))
        assert resultat == pytest.approx(-0.5)

    def test_serie_monotone_croissante_est_zero(self):
        assert quant.drawdown_maximum(_serie([100.0, 110.0, 120.0])) == pytest.approx(0.0)

    def test_moins_de_deux_points_est_none(self):
        assert quant.drawdown_maximum(_serie([100.0])) is None


class TestCorrelation:
    def test_series_identiques_sont_parfaitement_correlees(self):
        prix = [100.0 + i * 2 for i in range(10)]
        assert quant.correlation(_serie(prix), _serie(prix)) == pytest.approx(1.0)

    def test_series_inversees_sont_anti_correlees(self):
        # Construites a partir des MEMES rendements, l'un oppose a l'autre —
        # une simple pente inverse (200-i) ne suffit pas : les rendements en
        # POURCENTAGE ne sont pas symetriques entre deux niveaux de prix
        # differents, meme si les prix eux-memes le sont.
        rendements = [0.02, -0.01, 0.03, -0.02, 0.015, -0.005, 0.01, -0.02]

        def _depuis_rendements(rs, depart=100.0):
            prix = [depart]
            for r in rs:
                prix.append(prix[-1] * (1 + r))
            return prix

        a = _depuis_rendements(rendements)
        b = _depuis_rendements([-r for r in rendements])
        assert quant.correlation(_serie(a), _serie(b)) == pytest.approx(-1.0)

    def test_serie_constante_indefinie_est_none(self):
        # Une serie constante a une volatilite nulle : correlation indefinie,
        # jamais rendue comme 0.
        a = [100.0] * 10
        b = [100.0 + i for i in range(10)]
        assert quant.correlation(_serie(a), _serie(b)) is None


class TestAnalyser:
    def test_tendance_indeterminee_sans_assez_d_historique(self):
        resultat = quant.analyser("bitcoin", _serie([100.0, 101.0]))
        assert resultat.tendance == "INDETERMINEE"
        assert resultat.sma_50 is None

    def test_tendance_haussiere(self):
        # SMA20 (recente, plus haute) > SMA50 (plus ancienne, plus basse) : une
        # serie qui monte regulierement le garantit.
        prix = [100.0 + i for i in range(60)]
        resultat = quant.analyser("bitcoin", _serie(prix))
        assert resultat.tendance == "HAUSSIERE"
        assert resultat.sma_20 > resultat.sma_50

    def test_tendance_baissiere(self):
        prix = [200.0 - i for i in range(60)]
        resultat = quant.analyser("bitcoin", _serie(prix))
        assert resultat.tendance == "BAISSIERE"

    def test_to_dict_a_toutes_les_cles(self):
        resultat = quant.analyser("bitcoin", _serie([100.0, 101.0, 99.0]))
        d = resultat.to_dict()
        for cle in ("actif", "points", "rendement_total", "volatilite", "momentum",
                    "sma_20", "sma_50", "ema_12", "rsi_14", "macd", "bollinger",
                    "support_resistance", "drawdown_maximum", "tendance"):
            assert cle in d
