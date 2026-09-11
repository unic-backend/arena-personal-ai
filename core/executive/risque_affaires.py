"""Classification de risque d'affaires — deterministe, jamais devinee par le
modele (mission §13/§27, meme discipline que `core/finance/risk.py`).

**Reutilise, ne duplique pas** : `NiveauRisque` (FAIBLE/MODERE/ELEVE/EXTREME/
INCONNU) vient directement de `core/finance/risk.py` — c'est deja un
vocabulaire generique, seuls les SEUILS y sont specifiques au marche (volatilite,
drawdown). Ce module ajoute des seuils propres aux decisions d'affaires
(dependance fournisseur, marge de delai, exposition de tresorerie), sans
introduire un second enum de niveaux.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from core.finance.risk import NiveauRisque

#: Ordre du pire au meilleur — sert a combiner plusieurs niveaux (le risque
#: global d'une decision est au moins aussi mauvais que son pire facteur).
_ORDRE = (NiveauRisque.INCONNU, NiveauRisque.FAIBLE, NiveauRisque.MODERE,
          NiveauRisque.ELEVE, NiveauRisque.EXTREME)
_RANG = {niveau: rang for rang, niveau in enumerate(_ORDRE)}


def pire(*niveaux: NiveauRisque) -> NiveauRisque:
    """Le plus severe des niveaux fournis. `INCONNU` ne l'emporte jamais sur
    un niveau reellement mesure — un facteur non mesurable ne doit pas
    masquer un risque reel trouve par un autre facteur."""
    connus = [n for n in niveaux if n != NiveauRisque.INCONNU]
    if not connus:
        return NiveauRisque.INCONNU
    return max(connus, key=lambda n: _RANG[n])


def classer_dependance_fournisseur(part_du_total: Optional[float]) -> NiveauRisque:
    """`part_du_total` : la fraction (0-1) du cout ou du delai qui repose sur
    UN SEUL fournisseur/sous-traitant. Un fournisseur unique qui porte
    l'essentiel du chantier est un point de defaillance unique."""
    if part_du_total is None:
        return NiveauRisque.INCONNU
    if part_du_total < 0.3:
        return NiveauRisque.FAIBLE
    if part_du_total < 0.6:
        return NiveauRisque.MODERE
    if part_du_total < 0.85:
        return NiveauRisque.ELEVE
    return NiveauRisque.EXTREME


def classer_risque_delai(marge_jours: Optional[float], duree_totale_jours: Optional[float]) -> NiveauRisque:
    """`marge_jours` : ce qui reste une fois l'estimation ET le risque de
    retard connus soustraits du delai disponible (voir
    `core/executive/calcul_affaires.py::evaluer_faisabilite_delai`).
    Negatif d'emblee = EXTREME ; le ratio marge/duree distingue ensuite un
    delai simplement serre d'un delai confortable."""
    if marge_jours is None or not duree_totale_jours:
        return NiveauRisque.INCONNU
    if marge_jours < 0:
        return NiveauRisque.EXTREME
    ratio = marge_jours / duree_totale_jours
    if ratio < 0.05:
        return NiveauRisque.ELEVE
    if ratio < 0.15:
        return NiveauRisque.MODERE
    return NiveauRisque.FAIBLE


def classer_exposition_tresorerie(
    depense_avant_encaissement: Optional[float], tresorerie_disponible: Optional[float],
) -> NiveauRisque:
    """Le projet exige-t-il d'avancer plus d'argent que ce que l'entreprise a
    reellement en tresorerie avant le premier encaissement client ? Un ratio
    superieur a 1 est deja une alerte : l'entreprise devrait emprunter ou
    retarder un paiement fournisseur pour tenir jusqu'a l'acompte."""
    if depense_avant_encaissement is None or tresorerie_disponible is None:
        return NiveauRisque.INCONNU
    if tresorerie_disponible <= 0:
        return NiveauRisque.EXTREME if depense_avant_encaissement > 0 else NiveauRisque.FAIBLE
    ratio = depense_avant_encaissement / tresorerie_disponible
    if ratio < 0.5:
        return NiveauRisque.FAIBLE
    if ratio < 0.85:
        return NiveauRisque.MODERE
    if ratio <= 1.0:
        return NiveauRisque.ELEVE
    return NiveauRisque.EXTREME


def classer_concentration_client(part_du_chiffre_affaires: Optional[float]) -> NiveauRisque:
    """`part_du_chiffre_affaires` (0-1) : la part du CA total que represente
    UN client. Un client qui pese l'essentiel du chiffre d'affaires rend
    l'entreprise dependante d'une seule relation commerciale."""
    if part_du_chiffre_affaires is None:
        return NiveauRisque.INCONNU
    if part_du_chiffre_affaires < 0.2:
        return NiveauRisque.FAIBLE
    if part_du_chiffre_affaires < 0.4:
        return NiveauRisque.MODERE
    if part_du_chiffre_affaires < 0.6:
        return NiveauRisque.ELEVE
    return NiveauRisque.EXTREME


@dataclass(frozen=True)
class ResultatRisqueAffaires:
    """Le risque global d'une decision, et chaque facteur qui y contribue —
    jamais un seul chiffre qui cacherait lequel des facteurs domine."""

    niveau_global: NiveauRisque
    facteurs: Dict[str, NiveauRisque]

    def to_dict(self) -> Dict[str, object]:
        return {
            "overall_level": self.niveau_global.value,
            "factors": {cle: niveau.value for cle, niveau in self.facteurs.items()},
        }


def analyser(
    *,
    dependance_fournisseur: Optional[float] = None,
    marge_jours: Optional[float] = None,
    duree_totale_jours: Optional[float] = None,
    exposition_tresorerie: Optional[float] = None,
    tresorerie_disponible: Optional[float] = None,
    concentration_client: Optional[float] = None,
) -> ResultatRisqueAffaires:
    """Combine les facteurs fournis en un risque global. Un facteur non
    fourni est INCONNU pour ce facteur, et n'aggrave jamais artificiellement
    le total (voir `pire`)."""
    facteurs = {
        "supplier_dependency": classer_dependance_fournisseur(dependance_fournisseur),
        "deadline_risk": classer_risque_delai(marge_jours, duree_totale_jours),
        "cash_exposure": classer_exposition_tresorerie(exposition_tresorerie, tresorerie_disponible),
        "customer_concentration": classer_concentration_client(concentration_client),
    }
    return ResultatRisqueAffaires(niveau_global=pire(*facteurs.values()), facteurs=facteurs)
