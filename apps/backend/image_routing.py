"""Routage deterministe des pieces jointes image vers la vision.

Ce module reste volontairement petit : une image reellement acceptee par le
depot de pieces jointes doit pouvoir orienter une phrase elliptique ("regarde
ca", "et celle-ci ?") vers VISION sans demander au modele de deviner qu'une
image est jointe.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional


# Les formulations explicites non-visuelles ne doivent pas etre volees a un
# agent metier uniquement parce qu'une image accompagne le message.
_MOTS_ACTION_SPECIALISEE = (
    "publie", "poster", "envoie", "email", "mail", "montage", "video",
    "audio", "transcris", "code", "corrige le depot", "architecture 3d",
)


def doit_forcer_vision(
    prompt: str,
    attachments: Iterable[str],
    lire_piece: Callable[[str], object | None],
) -> bool:
    """Vrai si au moins une piece jointe est une image lisible.

    Le contenu de la piece est la source de verite ; le nom ou l'identifiant ne
    suffit jamais. ``lire_piece`` est injecte afin de garder cette fonction
    testable et sans dependance circulaire avec le runtime FastAPI.
    """
    texte = (prompt or "").strip().lower()
    if any(mot in texte for mot in _MOTS_ACTION_SPECIALISEE):
        return False

    for identifiant in attachments or ():
        piece = lire_piece(identifiant)
        if piece is None:
            continue
        if getattr(piece, "lisible", False) and getattr(piece, "est_image", False):
            return True
    return False


def intention_avec_image(
    prompt: str,
    attachments: Iterable[str],
    lire_piece: Callable[[str], object | None],
    intention: Optional[str],
) -> Optional[str]:
    """Remplace une intention generale par VISION quand une vraie image existe."""
    if doit_forcer_vision(prompt, attachments, lire_piece):
        return "VISION"
    return intention
