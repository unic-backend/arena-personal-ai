"""Contrat d'execution adaptatif pour les agents ARENA.

Ce module encode des invariants utiles observes dans plusieurs assistants
modernes sans importer leurs prompts, leurs identites ni leur configuration.
Le code reste propre a ARENA et mesurable par tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Complexite(str, Enum):
    SIMPLE = "simple"
    MULTI_ETAPES = "multi_etapes"
    LONGUE = "longue"


@dataclass(frozen=True)
class PolitiqueExecution:
    complexite: Complexite
    peut_deleguer: bool
    verifier_avant_final: bool
    garder_trace: bool
    budget_delegations: int


_MARQUEURS_MULTI = (
    "puis", "ensuite", "apres", "après", "et aussi", "en meme temps",
    "en même temps", "compare", "analyse", "verifie", "vérifie", "corrige",
    "integre", "intègre", "teste", "deploie", "déploie",
)
_MARQUEURS_LONGS = (
    "tout le depot", "tout le dépôt", "profond", "complet", "production",
    "de bout en bout", "end-to-end", "e2e", "sans regression", "sans régression",
)


def politique_pour(requete: str, pieces: Iterable[str] = ()) -> PolitiqueExecution:
    """Choisit une politique deterministe, sans demander au LLM de se noter."""
    texte = (requete or "").casefold()
    nb_pieces = sum(1 for _ in pieces)
    longue = any(m in texte for m in _MARQUEURS_LONGS) or nb_pieces >= 4
    multi = longue or sum(m in texte for m in _MARQUEURS_MULTI) >= 2

    if longue:
        return PolitiqueExecution(Complexite.LONGUE, True, True, True, 4)
    if multi:
        return PolitiqueExecution(Complexite.MULTI_ETAPES, True, True, True, 3)
    return PolitiqueExecution(Complexite.SIMPLE, False, False, False, 1)


def delegation_autorisee(
    politique: PolitiqueExecution,
    chaine: Iterable[str],
    specialiste: str,
) -> bool:
    """Ferme les boucles et tient le budget avant tout appel de sous-agent."""
    chemin = list(chaine)
    if not politique.peut_deleguer:
        return False
    if specialiste in chemin:
        return False
    return len(chemin) < politique.budget_delegations
