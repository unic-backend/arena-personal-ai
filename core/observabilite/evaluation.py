"""Evaluation locale structurée des exécutions d'agents.

Inspirée du découpage utile de rLLM (épisode -> trajectoire -> étapes -> signaux),
sans importer son moteur RL, ses trainers, ses sandboxes ni ses fournisseurs.
Ce module ne note jamais un LLM subjectivement : l'appelant fournit des signaux
mesurés et ARENA les agrège de façon déterministe.
"""
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple


@dataclass(frozen=True)
class SignalEvaluation:
    nom: str
    valeur: float


@dataclass(frozen=True)
class EtapeEvaluation:
    nom: str
    reussie: bool
    signaux: Tuple[SignalEvaluation, ...] = ()
    erreur: Optional[str] = None


@dataclass(frozen=True)
class TrajectoireEvaluation:
    scenario: str
    etapes: Tuple[EtapeEvaluation, ...]
    signaux: Tuple[SignalEvaluation, ...] = ()

    @property
    def reussie(self) -> bool:
        return bool(self.etapes) and all(etape.reussie for etape in self.etapes)


@dataclass(frozen=True)
class EpisodeEvaluation:
    nom: str
    trajectoires: Tuple[TrajectoireEvaluation, ...]
    metadonnees: Dict[str, str] = field(default_factory=dict)


def agreger(episodes: Iterable[EpisodeEvaluation]) -> Dict[str, object]:
    """Agrège succès et signaux mesurés, sans inventer de score absent."""
    trajectoires = [t for episode in episodes for t in episode.trajectoires]
    sommes: Dict[str, float] = {}
    comptes: Dict[str, int] = {}
    for trajectoire in trajectoires:
        signaux = list(trajectoire.signaux)
        for etape in trajectoire.etapes:
            signaux.extend(etape.signaux)
        for signal in signaux:
            sommes[signal.nom] = sommes.get(signal.nom, 0.0) + float(signal.valeur)
            comptes[signal.nom] = comptes.get(signal.nom, 0) + 1
    total = len(trajectoires)
    reussies = sum(t.reussie for t in trajectoires)
    return {
        "total": total,
        "reussies": reussies,
        "taux_reussite": reussies / total if total else None,
        "moyennes": {nom: sommes[nom] / comptes[nom] for nom in sommes},
    }
