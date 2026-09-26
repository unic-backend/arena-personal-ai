"""Garde-fous de production pour une video avec presentateur.

Adoption selective de lanshu-create-ai-presenter-video (MIT) : Arena garde
son orchestrateur, son journal et ses fournisseurs. Ce module ajoute seulement
les invariants de qualite/cout qui manquaient au pipeline existant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


class PhasePresentateur(str, Enum):
    INTAKE = "intake"
    CONTENU_VERROUILLE = "content_locked"
    AUDIO_VERROUILLE = "audio_locked"
    PLAN_VISUEL_VERROUILLE = "visual_plan_locked"
    PRESENTATEUR_GENERE = "presenter_generated"
    COMPOSITION_VERIFIEE = "composition_checked"
    RENDU = "rendered"
    VERIFIE = "verified"


_ORDRE = tuple(PhasePresentateur)


@dataclass(frozen=True)
class ControlePresentateur:
    autorise: bool
    phase: PhasePresentateur
    prochaine_phase: Optional[PhasePresentateur]
    blocages: Tuple[str, ...] = ()
    avertissements: Tuple[str, ...] = ()


@dataclass
class EtatPresentateur:
    """Etat minimal, serialisable, sans dupliquer JournalProjets."""

    phase: PhasePresentateur = PhasePresentateur.INTAKE
    essais_payants_rejetes: int = 0
    task_ids: list[str] = field(default_factory=list)

    def enregistrer_task_id(self, task_id: str) -> None:
        valeur = (task_id or "").strip()
        if valeur and valeur not in self.task_ids:
            self.task_ids.append(valeur)

    def candidat_payant_rejete(self) -> None:
        self.essais_payants_rejetes += 1

    def peut_relancer_payant(self, plafond: int = 3) -> bool:
        return self.essais_payants_rejetes < plafond

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "essais_payants_rejetes": self.essais_payants_rejetes,
            "task_ids": list(self.task_ids),
        }


def controler_transition(
    etat: EtatPresentateur,
    cible: PhasePresentateur,
    preuves: Mapping[str, Any],
) -> ControlePresentateur:
    """Autorise seulement la prochaine phase et exige des preuves mesurables."""
    index = _ORDRE.index(etat.phase)
    prochaine = _ORDRE[index + 1] if index + 1 < len(_ORDRE) else None
    blocages: list[str] = []
    avertissements: list[str] = []

    if cible is not prochaine:
        blocages.append(
            f"transition invalide : {etat.phase.value} -> {cible.value}; "
            f"attendu : {prochaine.value if prochaine else 'aucune'}"
        )
        return ControlePresentateur(False, etat.phase, prochaine, tuple(blocages))

    exigences = {
        PhasePresentateur.CONTENU_VERROUILLE: ("script",),
        PhasePresentateur.AUDIO_VERROUILLE: ("audio", "duree_audio"),
        PhasePresentateur.PLAN_VISUEL_VERROUILLE: ("plan_visuel",),
        PhasePresentateur.PRESENTATEUR_GENERE: ("presentateur", "task_id"),
        PhasePresentateur.COMPOSITION_VERIFIEE: ("composition_ok",),
        PhasePresentateur.RENDU: ("rendu",),
        PhasePresentateur.VERIFIE: ("decode_ok", "revue_visuelle_ok"),
    }
    for cle in exigences.get(cible, ()):
        if not preuves.get(cle):
            blocages.append(f"preuve manquante : {cle}")

    if cible is PhasePresentateur.PRESENTATEUR_GENERE:
        if not preuves.get("pilot_ok"):
            blocages.append("preuve manquante : pilot_ok")
        if not etat.peut_relancer_payant():
            blocages.append("plafond de 3 candidats payants rejetes atteint")
        if not preuves.get("cout_approuve"):
            avertissements.append("cout_approuve absent : generation distante bloquee")
            blocages.append("preuve manquante : cout_approuve")

    return ControlePresentateur(
        not blocages, etat.phase, prochaine, tuple(blocages), tuple(avertissements)
    )


def avancer(
    etat: EtatPresentateur,
    cible: PhasePresentateur,
    preuves: Mapping[str, Any],
) -> ControlePresentateur:
    controle = controler_transition(etat, cible, preuves)
    if controle.autorise:
        etat.phase = cible
        if cible is PhasePresentateur.PRESENTATEUR_GENERE:
            etat.enregistrer_task_id(str(preuves.get("task_id") or ""))
    return controle
