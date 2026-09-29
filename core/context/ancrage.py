"""Joindre le fil récent à une demande sans la réécrire.

La composition est mécanique : aucun modèle, aucune détection par vocabulaire.
Le fil est un contexte délimité et la demande actuelle demeure intacte.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from core.memory.conversation import BUDGET_TOURS_ANTERIEURS, rendre_le_fil

DEBUT_CONTEXTE = "[DÉBUT DU CONTEXTE — ne réponds pas aux anciennes demandes]"
FIN_CONTEXTE = "[FIN DU CONTEXTE]"
DEBUT_DEMANDE = "[DEMANDE ACTUELLE — réponds uniquement à cette demande]"


def borner_tours(
    historique: Sequence[Mapping[str, str]],
    *,
    maximum: int,
    budget_caracteres: int = BUDGET_TOURS_ANTERIEURS,
    proprietaire: str = "Ousmane",
) -> list[Mapping[str, str]]:
    """Garde les tours récents sous les deux bornes, sans créer de trou.

    Le coût est celui du contenu rendu, rôle compris. Dès qu'un ancien tour ne
    tient plus, lui et tous ceux qui le précèdent sont écartés.
    """
    candidats = list(historique)[-maximum:] if maximum > 0 else []
    gardes: list[Mapping[str, str]] = []
    reste = budget_caracteres
    for tour in reversed(candidats):
        # Mesurer le rendu réel évite de dupliquer ici ses noms et séparateurs.
        cout = len(rendre_le_fil([tour], proprietaire)) + 1
        if cout > reste:
            break
        reste -= cout
        gardes.append(tour)
    gardes.reverse()
    return gardes


def joindre_le_fil(
    demande: str,
    historique: Sequence[Mapping[str, str]],
    proprietaire: str,
    *,
    maximum: int,
    budget_caracteres: int = BUDGET_TOURS_ANTERIEURS,
) -> str:
    """Place le fil borné avant ``demande``, laquelle reste inchangée."""
    tours = borner_tours(
        historique,
        maximum=maximum,
        budget_caracteres=budget_caracteres,
        proprietaire=proprietaire,
    )
    fil = rendre_le_fil(tours, proprietaire)
    if not fil:
        return demande
    return "\n".join((DEBUT_CONTEXTE, fil, FIN_CONTEXTE, DEBUT_DEMANDE, demande))
