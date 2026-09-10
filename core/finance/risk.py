"""Moteur de risque — classification et scenarios, tous deterministes.

Audit AutoHedge (docs/audits/autohedge_audit.md) : son « Risk Management
Agent » ne recoit ni tests ni outil — c'est un prompt qui demande au modele
d'inventer "1. Recommended position size 2. Maximum drawdown risk...". Ce
module fait l'inverse : chaque metrique est un calcul verifiable, et le modele
n'intervient qu'ensuite, pour EXPLIQUER un chiffre deja produit — jamais pour
le choisir.

Les seuils ci-dessous sont des heuristiques documentees, pas une science exacte
— ils tranchent une classification LISIBLE (`FAIBLE`/`MODERE`/`ELEVE`/`EXTREME`)
a partir d'une mesure reelle. Aucun n'est invente au moment de classer : ils
sont fixes ici, dans le code, avant toute analyse — jamais ajustes pour faire
correspondre un resultat souhaite.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class NiveauRisque(str, Enum):
    FAIBLE = "LOW"
    MODERE = "MODERATE"
    ELEVE = "HIGH"
    EXTREME = "EXTREME"
    INCONNU = "UNKNOWN"  # pas assez de donnees pour classer — jamais FAIBLE par defaut


#: Seuils de volatilite (ecart-type des rendements PERIODE A PERIODE, tel que
#: rendu par `core/finance/quant.py::volatilite`). Mesures sur des cryptos
#: majeures (BTC/ETH, rendements journaliers) : une volatilite journaliere de
#: 2% est ordinaire, 5% est deja agitee, 10%+ signale un evenement.
SEUILS_VOLATILITE = (0.02, 0.05, 0.10)  # FAIBLE < 2% < MODERE < 5% < ELEVE < 10% < EXTREME

#: Seuils de repli maximal (valeur negative — -0.15 = -15%).
SEUILS_DRAWDOWN = (-0.10, -0.25, -0.50)  # FAIBLE > -10% > MODERE > -25% > ELEVE > -50% > EXTREME


def classer_volatilite(volatilite: Optional[float]) -> NiveauRisque:
    if volatilite is None:
        return NiveauRisque.INCONNU
    v = abs(volatilite)
    faible, modere, eleve = SEUILS_VOLATILITE
    if v < faible:
        return NiveauRisque.FAIBLE
    if v < modere:
        return NiveauRisque.MODERE
    if v < eleve:
        return NiveauRisque.ELEVE
    return NiveauRisque.EXTREME


def classer_drawdown(drawdown: Optional[float]) -> NiveauRisque:
    if drawdown is None:
        return NiveauRisque.INCONNU
    faible, modere, eleve = SEUILS_DRAWDOWN
    if drawdown > faible:
        return NiveauRisque.FAIBLE
    if drawdown > modere:
        return NiveauRisque.MODERE
    if drawdown > eleve:
        return NiveauRisque.ELEVE
    return NiveauRisque.EXTREME


def indice_concentration(poids: Dict[str, float]) -> Optional[float]:
    """Indice de Herfindahl-Hirschman des poids d'un portefeuille (somme des
    poids au carre, chacun entre 0 et 1). 1.0 = tout sur un seul actif,
    1/N = parfaitement reparti sur N actifs. `None` si les poids ne somment
    pas a peu pres a 1 (donnee incoherente) ou si le portefeuille est vide."""
    total = sum(poids.values())
    if not poids or not (0.99 <= total <= 1.01):
        return None
    return sum(p ** 2 for p in poids.values())


def classer_concentration(poids: Dict[str, float]) -> NiveauRisque:
    hhi = indice_concentration(poids)
    if hhi is None:
        return NiveauRisque.INCONNU
    # Un seul actif (HHI=1.0) est EXTREME par construction ; 4 positions
    # egales ou plus (HHI <= 0.25) reste FAIBLE — d'ou le `>` strict ici,
    # jamais `>=`, pour que 0.25 pile reste inclus dans FAIBLE.
    if hhi >= 0.60:
        return NiveauRisque.EXTREME
    if hhi >= 0.35:
        return NiveauRisque.ELEVE
    if hhi > 0.25:
        return NiveauRisque.MODERE
    return NiveauRisque.FAIBLE


_ORDRE = [NiveauRisque.INCONNU, NiveauRisque.FAIBLE, NiveauRisque.MODERE,
          NiveauRisque.ELEVE, NiveauRisque.EXTREME]


def _pire(*niveaux: NiveauRisque) -> NiveauRisque:
    """Le niveau le plus severe l'emporte — jamais une moyenne, qui masquerait
    le facteur le plus dangereux derriere les autres."""
    connus = [n for n in niveaux if n is not NiveauRisque.INCONNU]
    if not connus:
        return NiveauRisque.INCONNU
    return max(connus, key=_ORDRE.index)


def taille_position(
    capital: float, risque_max_fraction: float, prix_entree: float, prix_stop: float,
) -> Optional[float]:
    """Taille de position par le risque (formule standard de gestion de
    risque) : combien d'unites acheter pour ne perdre au plus que
    `risque_max_fraction` du capital si le prix touche `prix_stop`.

    `None` si les prix sont egaux (perte nulle par unite : la formule diverge)
    ou incoherents (l'un des deux <= 0).
    """
    if capital <= 0 or prix_entree <= 0 or prix_stop <= 0:
        return None
    perte_par_unite = abs(prix_entree - prix_stop)
    if perte_par_unite == 0:
        return None
    risque_capital = capital * risque_max_fraction
    return risque_capital / perte_par_unite


def scenario_stop_loss(prix_entree: float, volatilite: Optional[float], multiplicateur: float = 2.0) -> Optional[float]:
    """Stop-loss suggere : `multiplicateur` fois l'ecart-type des rendements
    en dessous du prix d'entree. `None` sans volatilite mesuree — un stop
    ne se devine pas sans mesure de la dispersion reelle."""
    if volatilite is None or prix_entree <= 0:
        return None
    return prix_entree * (1 - multiplicateur * abs(volatilite))


@dataclass(frozen=True)
class ResultatRisque:
    """Ce qui a ete mesure, et le niveau qui en decoule. `niveau_global` est
    le PIRE des niveaux connus — jamais une moyenne qui dilue le facteur le
    plus dangereux."""

    actif: str
    niveau_volatilite: NiveauRisque
    niveau_drawdown: NiveauRisque
    niveau_concentration: NiveauRisque
    niveau_global: NiveauRisque
    stop_loss_suggere: Optional[float] = None
    taille_position_suggeree: Optional[float] = None
    detail: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "actif": self.actif,
            "niveau_volatilite": self.niveau_volatilite.value,
            "niveau_drawdown": self.niveau_drawdown.value,
            "niveau_concentration": self.niveau_concentration.value,
            "niveau_global": self.niveau_global.value,
            "stop_loss_suggere": self.stop_loss_suggere,
            "taille_position_suggeree": self.taille_position_suggeree,
        }


def analyser(
    actif: str, *, volatilite: Optional[float], drawdown_maximum: Optional[float],
    prix_actuel: Optional[float] = None, poids_portefeuille: Optional[Dict[str, float]] = None,
    capital: Optional[float] = None, risque_max_fraction: float = 0.01,
) -> ResultatRisque:
    """Point d'entree unique du moteur de risque. Toutes les metriques
    d'entree viennent de `core/finance/quant.py` ou d'un portefeuille reel —
    jamais devinees ici."""
    niveau_vol = classer_volatilite(volatilite)
    niveau_dd = classer_drawdown(drawdown_maximum)
    niveau_conc = classer_concentration(poids_portefeuille or {}) if poids_portefeuille else NiveauRisque.INCONNU

    stop = scenario_stop_loss(prix_actuel, volatilite) if prix_actuel else None
    taille = (
        taille_position(capital, risque_max_fraction, prix_actuel, stop)
        if (capital and prix_actuel and stop) else None
    )

    return ResultatRisque(
        actif=actif, niveau_volatilite=niveau_vol, niveau_drawdown=niveau_dd,
        niveau_concentration=niveau_conc,
        niveau_global=_pire(niveau_vol, niveau_dd, niveau_conc),
        stop_loss_suggere=stop, taille_position_suggeree=taille,
    )
