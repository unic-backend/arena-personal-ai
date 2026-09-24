"""Resultats d'evaluation structures pour les benchmarks ARENA.

Inspire du modele signal/resultat de rLLM, sans importer son runtime
d'entrainement. Ce module reste deterministe et sans dependance externe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import comb


@dataclass(frozen=True)
class SignalEvaluation:
    nom: str
    valeur: float


@dataclass(frozen=True)
class TentativeEvaluation:
    scenario: str
    correcte: bool
    signaux: tuple[SignalEvaluation, ...] = ()
    erreur: str | None = None


@dataclass(frozen=True)
class RapportEvaluation:
    total: int
    correctes: int
    erreurs: int
    score: float
    moyennes: dict[str, float] = field(default_factory=dict)


def agreger(tentatives: list[TentativeEvaluation]) -> RapportEvaluation:
    total = len(tentatives)
    correctes = sum(t.correcte for t in tentatives)
    erreurs = sum(t.erreur is not None for t in tentatives)
    sommes: dict[str, float] = {}
    comptes: dict[str, int] = {}
    for tentative in tentatives:
        for signal in tentative.signaux:
            sommes[signal.nom] = sommes.get(signal.nom, 0.0) + signal.valeur
            comptes[signal.nom] = comptes.get(signal.nom, 0) + 1
    moyennes = {nom: sommes[nom] / comptes[nom] for nom in sommes}
    return RapportEvaluation(
        total=total,
        correctes=correctes,
        erreurs=erreurs,
        score=correctes / total if total else 0.0,
        moyennes=moyennes,
    )


def pass_at_k(groupes: list[tuple[int, int]], k: int) -> float:
    """Estimateur pass@k non biaise sur (tentatives, succes) par scenario."""
    if k < 1:
        raise ValueError("k doit etre >= 1")
    scores: list[float] = []
    for n, c in groupes:
        if n < 0 or c < 0 or c > n:
            raise ValueError("compte de tentatives invalide")
        if n < k:
            scores.append(1.0 if c else 0.0)
        elif n - c < k:
            scores.append(1.0)
        else:
            scores.append(1.0 - comb(n - c, k) / comb(n, k))
    return sum(scores) / len(scores) if scores else 0.0
