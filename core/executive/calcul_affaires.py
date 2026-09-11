"""Calcul financier deterministe pour l'Executive Intelligence (mission §13).

**Ce que ce module n'est pas** : un second moteur de chiffrage. Le chiffrage
au metre (materiaux, main-d'oeuvre par ligne de devis) reste dans
`agents/plaquiste/calcul_materiaux.py` — jamais duplique ici. Ce module
calcule sur des montants DEJA connus (revenu, cout total, echeances) — la
marge, l'echeancier de tresorerie et la comparaison de scenarios — ce qui est
generique a n'importe quelle decision d'affaires, pas seulement au BA13.

**Pourquoi deterministe.** Un modele de langage additionne parfois mal de
tete (mission §13). Chaque fonction ici est un calcul verifiable, teste, sans
appel modele — exactement la discipline deja choisie par
`core/finance/quant.py`/`core/finance/risk.py` pour l'analyse de marche.

**Aucune valeur n'est inventee.** Une entree manquante ou incoherente
(pourcentages d'echeancier qui ne totalisent pas 100, cout negatif) rend un
resultat marque invalide avec sa raison — jamais un chiffre par defaut.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

#: Tolerance d'arrondi acceptee sur un echeancier declare a 100% — les
#: pourcentages fournis a la main portent souvent une decimale (33.3+33.3+33.4).
TOLERANCE_ECHEANCIER_POURCENT = 0.5


@dataclass(frozen=True)
class ResultatMarge:
    """Marge brute a partir d'un revenu et d'une repartition des couts."""

    valide: bool
    raison: Optional[str] = None
    revenu: float = 0.0
    cout_total: float = 0.0
    detail_couts: Dict[str, float] = field(default_factory=dict)
    marge_brute: Optional[float] = None
    marge_pourcent: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "valid": self.valide, "reason": self.raison,
            "revenue": self.revenu, "total_cost": self.cout_total,
            "cost_breakdown": dict(self.detail_couts),
            "gross_margin": self.marge_brute,
            "gross_margin_percent": self.marge_pourcent,
        }


def calculer_marge(revenu: float, couts: Dict[str, float]) -> ResultatMarge:
    """Marge brute = revenu - somme des couts ; jamais calculee sur des
    entrees negatives ou absentes, qui refusent le calcul plutot que de
    rendre un nombre trompeur."""
    if revenu is None or revenu <= 0:
        return ResultatMarge(valide=False, raison="revenu manquant ou non positif")
    if not couts:
        return ResultatMarge(valide=False, raison="aucun cout fourni", revenu=revenu)
    for poste, valeur in couts.items():
        if valeur < 0:
            return ResultatMarge(
                valide=False, raison=f"cout negatif refuse : {poste}={valeur}",
                revenu=revenu, detail_couts=dict(couts),
            )
    cout_total = sum(couts.values())
    marge = revenu - cout_total
    pourcent = (marge / revenu) * 100 if revenu else None
    return ResultatMarge(
        valide=True, revenu=revenu, cout_total=cout_total, detail_couts=dict(couts),
        marge_brute=marge, marge_pourcent=pourcent,
    )


@dataclass(frozen=True)
class EtapeEcheance:
    """Une ligne d'echeancier : un libelle, un pourcentage du total."""

    libelle: str
    pourcentage: float
    montant: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        return {"label": self.libelle, "percent": self.pourcentage, "amount": self.montant}


@dataclass(frozen=True)
class ResultatEcheancier:
    """Le montant reel de chaque echeance, et le total verifie."""

    valide: bool
    raison: Optional[str] = None
    montant_total: float = 0.0
    etapes: List[EtapeEcheance] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "valid": self.valide, "reason": self.raison,
            "total_amount": self.montant_total,
            "steps": [e.to_dict() for e in self.etapes],
        }


def calculer_echeancier(
    montant_total: float, echeances: List[Tuple[str, float]],
) -> ResultatEcheancier:
    """Convertit un echeancier en pourcentages (ex. 50/30/20) en montants
    reels. Refuse un echeancier dont les pourcentages ne totalisent pas
    ~100% — un echeancier qui ne boucle pas sur lui-meme cache un manque ou
    un double compte, jamais une approximation anodine."""
    if montant_total is None or montant_total <= 0:
        return ResultatEcheancier(valide=False, raison="montant total manquant ou non positif")
    if not echeances:
        return ResultatEcheancier(valide=False, raison="aucune echeance fournie",
                                   montant_total=montant_total)
    total_pourcent = sum(p for _, p in echeances)
    if abs(total_pourcent - 100.0) > TOLERANCE_ECHEANCIER_POURCENT:
        return ResultatEcheancier(
            valide=False,
            raison=f"les pourcentages totalisent {total_pourcent:.1f}%, pas 100%",
            montant_total=montant_total,
        )
    etapes = [
        EtapeEcheance(libelle=libelle, pourcentage=pourcent,
                      montant=round(montant_total * pourcent / 100, 2))
        for libelle, pourcent in echeances
    ]
    return ResultatEcheancier(valide=True, montant_total=montant_total, etapes=etapes)


@dataclass(frozen=True)
class ResultatFaisabiliteDelai:
    """Le delai demande tient-il compte de la marge de risque connue ?"""

    valide: bool
    raison: Optional[str] = None
    jours_disponibles: float = 0.0
    jours_estimes: float = 0.0
    jours_risque: float = 0.0
    marge_jours: Optional[float] = None
    faisable: Optional[bool] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "valid": self.valide, "reason": self.raison,
            "days_available": self.jours_disponibles,
            "days_estimated": self.jours_estimes,
            "days_risk": self.jours_risque,
            "margin_days": self.marge_jours,
            "feasible": self.faisable,
        }


def evaluer_faisabilite_delai(
    jours_disponibles: float, jours_estimes: float, jours_risque: float = 0.0,
) -> ResultatFaisabiliteDelai:
    """Faisable seulement si le delai disponible couvre l'estimation ET le
    risque de retard connu (ex. retard fournisseur possible) — jamais
    seulement l'estimation optimiste."""
    if jours_disponibles is None or jours_disponibles <= 0:
        return ResultatFaisabiliteDelai(valide=False, raison="delai disponible manquant ou non positif")
    if jours_estimes is None or jours_estimes < 0:
        return ResultatFaisabiliteDelai(
            valide=False, raison="duree estimee manquante ou negative",
            jours_disponibles=jours_disponibles,
        )
    jours_risque = max(jours_risque or 0.0, 0.0)
    marge = jours_disponibles - (jours_estimes + jours_risque)
    return ResultatFaisabiliteDelai(
        valide=True, jours_disponibles=jours_disponibles, jours_estimes=jours_estimes,
        jours_risque=jours_risque, marge_jours=marge, faisable=marge >= 0,
    )


@dataclass(frozen=True)
class ScenarioAffaires:
    """Une variante : le meme revenu, des couts ou un delai qui changent."""

    nom: str
    revenu: float
    couts: Dict[str, float]
    jours_disponibles: Optional[float] = None
    jours_estimes: Optional[float] = None


@dataclass(frozen=True)
class ResultatComparaisonScenario:
    """Un scenario compare a la base — le delta, jamais seulement le
    resultat brut : c'est le delta qui repond a « et si… » (mission §14)."""

    nom: str
    marge: ResultatMarge
    delta_marge: Optional[float] = None
    delta_marge_pourcent: Optional[float] = None
    faisabilite: Optional[ResultatFaisabiliteDelai] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.nom, "margin": self.marge.to_dict(),
            "delta_margin": self.delta_marge,
            "delta_margin_percent": self.delta_marge_pourcent,
            "feasibility": self.faisabilite.to_dict() if self.faisabilite else None,
        }


def comparer_scenarios(
    base: ScenarioAffaires, variantes: List[ScenarioAffaires],
) -> List[ResultatComparaisonScenario]:
    """Compare chaque variante a la base — jamais les variantes entre elles
    seules, ce qui perdrait la reference de depart."""
    marge_base = calculer_marge(base.revenu, base.couts)
    resultats: List[ResultatComparaisonScenario] = []
    for variante in variantes:
        marge = calculer_marge(variante.revenu, variante.couts)
        delta = None
        delta_pct = None
        if marge.valide and marge_base.valide:
            delta = marge.marge_brute - marge_base.marge_brute
            if marge_base.marge_brute:
                delta_pct = (delta / abs(marge_base.marge_brute)) * 100
        faisabilite = None
        if variante.jours_disponibles is not None and variante.jours_estimes is not None:
            faisabilite = evaluer_faisabilite_delai(
                variante.jours_disponibles, variante.jours_estimes)
        resultats.append(ResultatComparaisonScenario(
            nom=variante.nom, marge=marge, delta_marge=delta,
            delta_marge_pourcent=delta_pct, faisabilite=faisabilite,
        ))
    return resultats
