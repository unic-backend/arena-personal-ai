"""Principes d'exploitation natifs pour l'intelligence executive d'ARENA.

Ce module ne copie ni Paperclip ni le livre source. Il transforme les idees
organisationnelles utiles en contraintes compactes et generiques qu'ARENA
injecte dans CHAQUE analyse executive : roles explicites, delegation,
controle humain proportionne au risque, budgets bornes, audit et arret.

Source conceptuelle :
Anthony David Adams, "Headcount Zero: How to Build an AI-Run Company with
Paperclip", notamment chapitres 5, 8, 9 et 12.
https://github.com/AnthonyDavidAdams/zero-employee-company-book

Le depot source ne declare pas de licence dans ses metadonnees GitHub au
23/09/2026. Pour cette raison, aucun texte, code ou fichier du depot n'est
vendore ici. Les principes ci-dessous sont une implementation originale et
courte dans l'architecture existante d'ARENA.
"""
from __future__ import annotations

from typing import Final

SOURCE: Final[str] = (
    "Anthony David Adams — Headcount Zero / zero-employee-company-book"
)

PRINCIPES: Final[tuple[str, ...]] = (
    "Traiter les agents comme des roles avec responsabilite, autorite, limites "
    "et critere de fin explicites, pas comme une collection d'outils.",
    "Transformer un objectif en travail concret, deleguer au specialiste le plus "
    "pertinent, puis faire remonter resultat, inconnues et blocages.",
    "Automatiser le travail interne reversible; exiger une validation humaine "
    "avant une action externe, financiere, structurelle ou difficilement reversible.",
    "Borner chaque execution par un budget de cout, temps, etapes ou appels; "
    "arreter proprement quand une limite est atteinte plutot que poursuivre sans fin.",
    "Conserver une trace exploitable des plans, actions, echecs et decisions afin "
    "de pouvoir expliquer, corriger et ne pas repeter une erreur.",
    "Preferer une petite equipe de capacites reelles et joignables a une grande "
    "liste d'agents decoratifs; une capacite indisponible doit etre declaree telle quelle.",
    "Le proprietaire garde l'autorite finale: pause, refus, redirection et arret "
    "doivent rester possibles sur toute action a consequence.",
)


def bloc_pour_prompt() -> str:
    """Rend les principes sous forme directement injectable dans un prompt."""
    lignes = ["Principes d'exploitation ARENA (a appliquer, pas a reciter):"]
    lignes.extend(f"- {principe}" for principe in PRINCIPES)
    lignes.append(
        "- Ces principes guident la methode. Ils ne remplacent jamais les faits, "
        "preuves, permissions ni contraintes propres a la demande."
    )
    return "\n".join(lignes)
