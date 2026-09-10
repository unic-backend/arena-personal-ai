"""Analyse quantitative — arithmetique pure, jamais un appel reseau ni un
modele.

Audit AutoHedge (docs/audits/autohedge_audit.md) : son « Quant Agent » n'est
qu'un prompt — aucun outil de calcul ne lui est attache, et le depot entier ne
contient ni `numpy` ni `pandas` en dehors de code mort. Les « scores 0-1 » que
son README annonce sont donc devines par le modele, jamais mesures. C'est
exactement l'erreur que ce module existe pour rendre impossible : chaque
fonction ici prend des nombres et rend des nombres, sans jamais consulter un
modele. `agents/finance/finance_agent.py` fait ensuite interpreter ces
resultats par le modele — il ne les recalcule jamais.

Toutes les fonctions prennent une serie de prix : une liste de `(horodatage_ms,
prix)`, triee du plus ancien au plus recent — la forme exacte que rend
`ConnecteurMarketData.historique` (`core/connectors/market_data.py`).

Aucune fonction ne leve pour une serie trop courte : elle rend `None` la ou la
valeur ne peut pas se calculer honnetement (§34, "un champ absent n'est pas
zero" — une volatilite non calculable n'est pas une volatilite nulle).
"""
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

PointPrix = Tuple[float, float]  # (horodatage_ms, prix)


def _prix(serie: Sequence[PointPrix]) -> List[float]:
    return [p for _, p in serie]


def rendements(serie: Sequence[PointPrix]) -> List[float]:
    """Rendements simples periode a periode : (p[i] - p[i-1]) / p[i-1].

    Un prix a zero ou negatif rend une serie plus courte plutot qu'une
    division par zero — un prix reel n'est jamais nul, une donnee qui l'est
    est une donnee corrompue, pas un rendement infini.
    """
    prix = _prix(serie)
    resultat = []
    for precedent, courant in zip(prix, prix[1:], strict=False):
        if precedent > 0:
            resultat.append((courant - precedent) / precedent)
    return resultat


def rendement_total(serie: Sequence[PointPrix]) -> Optional[float]:
    """Rendement entre le premier et le dernier point de la serie."""
    prix = _prix(serie)
    if len(prix) < 2 or prix[0] <= 0:
        return None
    return (prix[-1] - prix[0]) / prix[0]


def volatilite(serie: Sequence[PointPrix]) -> Optional[float]:
    """Ecart-type des rendements. `None` avec moins de deux rendements —
    un seul point ne dit rien sur la dispersion."""
    r = rendements(serie)
    if len(r) < 2:
        return None
    return statistics.pstdev(r)


def moyenne_mobile(serie: Sequence[PointPrix], periode: int) -> Optional[float]:
    """Moyenne mobile simple (SMA) sur les `periode` derniers points."""
    prix = _prix(serie)
    if periode < 1 or len(prix) < periode:
        return None
    return sum(prix[-periode:]) / periode


def moyenne_mobile_exponentielle(serie: Sequence[PointPrix], periode: int) -> Optional[float]:
    """Moyenne mobile exponentielle (EMA), lissage standard 2/(periode+1)."""
    prix = _prix(serie)
    if periode < 1 or len(prix) < periode:
        return None
    lissage = 2.0 / (periode + 1)
    ema = sum(prix[:periode]) / periode  # amorcee par la SMA des `periode` premiers points
    for p in prix[periode:]:
        ema = p * lissage + ema * (1 - lissage)
    return ema


def momentum(serie: Sequence[PointPrix], periode: int = 10) -> Optional[float]:
    """Variation relative sur les `periode` derniers points."""
    prix = _prix(serie)
    if periode < 1 or len(prix) <= periode or prix[-1 - periode] <= 0:
        return None
    return (prix[-1] - prix[-1 - periode]) / prix[-1 - periode]


def rsi(serie: Sequence[PointPrix], periode: int = 14) -> Optional[float]:
    """Relative Strength Index, methode de Wilder. `None` sous `periode`+1 points."""
    prix = _prix(serie)
    if len(prix) < periode + 1:
        return None

    gains, pertes = [], []
    for precedent, courant in zip(prix, prix[1:], strict=False):
        variation = courant - precedent
        gains.append(max(variation, 0.0))
        pertes.append(max(-variation, 0.0))

    gain_moyen = sum(gains[:periode]) / periode
    perte_moyenne = sum(pertes[:periode]) / periode
    for gain, perte in zip(gains[periode:], pertes[periode:], strict=True):
        gain_moyen = (gain_moyen * (periode - 1) + gain) / periode
        perte_moyenne = (perte_moyenne * (periode - 1) + perte) / periode

    if perte_moyenne == 0:
        return 100.0
    force_relative = gain_moyen / perte_moyenne
    return 100 - (100 / (1 + force_relative))


def macd(
    serie: Sequence[PointPrix], rapide: int = 12, lent: int = 26, signal: int = 9,
) -> Optional[Dict[str, float]]:
    """MACD standard : ligne (EMA rapide - EMA lente), signal (EMA de la ligne),
    histogramme (ligne - signal). `None` si l'historique est trop court."""
    prix = _prix(serie)
    if len(prix) < lent + signal:
        return None

    def _serie_ema(valeurs: List[float], periode: int) -> List[float]:
        lissage = 2.0 / (periode + 1)
        ema = sum(valeurs[:periode]) / periode
        resultat = [ema]
        for v in valeurs[periode:]:
            ema = v * lissage + ema * (1 - lissage)
            resultat.append(ema)
        return resultat

    ema_rapide = _serie_ema(prix, rapide)
    ema_lente = _serie_ema(prix, lent)
    # Les deux series n'ont pas la meme longueur (la lente commence plus
    # tard) : on aligne sur la fin, la seule zone ou les deux existent.
    decalage = len(ema_rapide) - len(ema_lente)
    lignes = [rapide - lente for rapide, lente in zip(ema_rapide[decalage:], ema_lente, strict=True)]
    if len(lignes) < signal:
        return None
    ligne_signal = _serie_ema(lignes, signal)
    return {
        "ligne": lignes[-1],
        "signal": ligne_signal[-1],
        "histogramme": lignes[-1] - ligne_signal[-1],
    }


def bandes_bollinger(
    serie: Sequence[PointPrix], periode: int = 20, ecarts: float = 2.0,
) -> Optional[Dict[str, float]]:
    """Bande centrale (SMA), superieure et inferieure (± `ecarts` ecarts-types)."""
    prix = _prix(serie)
    if len(prix) < periode:
        return None
    fenetre = prix[-periode:]
    centre = sum(fenetre) / periode
    ecart_type = statistics.pstdev(fenetre)
    return {
        "centre": centre,
        "superieure": centre + ecarts * ecart_type,
        "inferieure": centre - ecarts * ecart_type,
    }


def support_resistance(serie: Sequence[PointPrix], periode: int = 30) -> Optional[Dict[str, float]]:
    """Support/resistance naifs : plus bas / plus haut des `periode` derniers
    points, et leur pivot (moyenne des deux, avec le dernier prix)."""
    prix = _prix(serie)
    if not prix:
        return None
    fenetre = prix[-periode:] if len(prix) >= periode else prix
    support, resistance = min(fenetre), max(fenetre)
    return {
        "support": support, "resistance": resistance,
        "pivot": (support + resistance + prix[-1]) / 3,
    }


def drawdown_maximum(serie: Sequence[PointPrix]) -> Optional[float]:
    """Pire chute depuis un sommet anterieur, en fraction negative (-0.32 = -32%)."""
    prix = _prix(serie)
    if len(prix) < 2:
        return None
    sommet = prix[0]
    pire = 0.0
    for p in prix:
        sommet = max(sommet, p)
        if sommet > 0:
            pire = min(pire, (p - sommet) / sommet)
    return pire


def correlation(serie_a: Sequence[PointPrix], serie_b: Sequence[PointPrix]) -> Optional[float]:
    """Correlation de Pearson entre deux series de RENDEMENTS (pas de prix —
    des prix de niveaux tres differents seraient corrompus par leur echelle).
    `None` si l'une des deux n'a pas assez de points, ou si l'une est constante
    (correlation indefinie, jamais rendue comme 0)."""
    ra, rb = rendements(serie_a), rendements(serie_b)
    n = min(len(ra), len(rb))
    if n < 2:
        return None
    ra, rb = ra[-n:], rb[-n:]
    if statistics.pstdev(ra) == 0 or statistics.pstdev(rb) == 0:
        return None
    return statistics.correlation(ra, rb)


@dataclass(frozen=True)
class ResultatQuant:
    """Tout ce qui a pu etre calcule pour un actif. Un champ `None` veut dire
    "pas assez d'historique pour le calculer", jamais "vaut zero"."""

    actif: str
    points: int
    rendement_total: Optional[float] = None
    volatilite: Optional[float] = None
    momentum: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_12: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[Dict[str, float]] = None
    bollinger: Optional[Dict[str, float]] = None
    support_resistance: Optional[Dict[str, float]] = None
    drawdown_maximum: Optional[float] = None
    tendance: str = "INDETERMINEE"
    detail: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "actif": self.actif, "points": self.points,
            "rendement_total": self.rendement_total, "volatilite": self.volatilite,
            "momentum": self.momentum, "sma_20": self.sma_20, "sma_50": self.sma_50,
            "ema_12": self.ema_12, "rsi_14": self.rsi_14, "macd": self.macd,
            "bollinger": self.bollinger, "support_resistance": self.support_resistance,
            "drawdown_maximum": self.drawdown_maximum, "tendance": self.tendance,
        }


def _tendance(sma_20: Optional[float], sma_50: Optional[float], dernier_prix: Optional[float]) -> str:
    """Tendance déterministe : croisement des deux moyennes mobiles, jamais
    une supposition. `INDETERMINEE` quand l'une des deux moyennes manque —
    jamais devinee a partir d'une seule."""
    if sma_20 is None or sma_50 is None or dernier_prix is None:
        return "INDETERMINEE"
    if sma_20 > sma_50:
        return "HAUSSIERE"
    if sma_20 < sma_50:
        return "BAISSIERE"
    return "NEUTRE"


def analyser(actif: str, serie: Sequence[PointPrix]) -> ResultatQuant:
    """Calcule tout ce que l'historique fourni permet — rien de plus, rien
    de devine. C'est la seule fonction que `FinanceAgent` appelle."""
    prix = _prix(serie)
    sma_20, sma_50 = moyenne_mobile(serie, 20), moyenne_mobile(serie, 50)
    return ResultatQuant(
        actif=actif, points=len(serie),
        rendement_total=rendement_total(serie), volatilite=volatilite(serie),
        momentum=momentum(serie), sma_20=sma_20, sma_50=sma_50,
        ema_12=moyenne_mobile_exponentielle(serie, 12), rsi_14=rsi(serie),
        macd=macd(serie), bollinger=bandes_bollinger(serie),
        support_resistance=support_resistance(serie),
        drawdown_maximum=drawdown_maximum(serie),
        tendance=_tendance(sma_20, sma_50, prix[-1] if prix else None),
    )
