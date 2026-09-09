"""Un plan : ce qu'on propose de faire, jamais ce qu'on a déjà fait.

Mission §14 : « Ne donne pas à un agent une capacité de "move arbitrary file
anywhere" sans contrôle. » Un `Plan` est une liste d'opérations REVUES avant
d'être appliquées — le connecteur ne laisse jamais un modèle atteindre
`Atelier.deplacer()` directement pour cette capacité ; il passe toujours par
ici, avec un statut qui trace où en est chaque plan.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TypeOperation(str, Enum):
    """Le vocabulaire FERMÉ des mutations qu'un plan peut contenir.

    Fermé délibérément : un plan ne peut pas porter une commande shell, un
    chemin de suppression de dossier entier, ou quoi que ce soit
    qu'`Atelier` ne sait pas déjà faire un par un. « move arbitrary file
    anywhere » (mission §14) devient ici une liste de cinq verbes connus,
    chacun réversible ou refusé s'il ne l'est pas.
    """

    DEPLACER = "deplacer"          # inclut le renommage : meme dossier, nom different
    COPIER = "copier"
    CREER_DOSSIER = "creer_dossier"
    SUPPRIMER = "supprimer"        # jamais sans confirmation — voir le connecteur


class StatutPlan(str, Enum):
    PROPOSE = "PROPOSED"       # ecrit, pas encore verifie
    VALIDE = "VALIDATED"       # verifie, pret a etre applique
    REFUSE = "REJECTED"        # la validation a trouve un probleme reel
    APPLIQUE = "APPLIED"       # execute, reversible
    ANNULE = "UNDONE"          # applique puis annule
    ECHEC = "FAILED"           # l'application a echoue en cours de route


@dataclass
class Operation:
    """Une mutation proposée, avec sa justification — jamais un chemin nu."""

    type: TypeOperation
    source: str
    destination: str = ""       # vide pour SUPPRIMER (rien a coter)
    raison: str = ""            # ce que le modele/le propriétaire dit vouloir

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type.value, "source": self.source,
                "destination": self.destination, "raison": self.raison}


@dataclass
class RapportOperation:
    """Ce qu'une opération a VRAIMENT donné une fois tentée."""

    operation: Operation
    ok: bool
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"operation": self.operation.to_dict(), "ok": self.ok, "message": self.message}


@dataclass
class Plan:
    """Une proposition d'organisation, identifiée, tracée du bout à l'autre.

    Attributes:
        identifiant: stable, pour `planifier` -> `appliquer` -> `annuler`.
        operations: la liste proposée, jamais mutée après `PROPOSE`.
        statut: où en est ce plan — voir `StatutPlan`.
        raisons_refus: pourquoi la validation a refusé, une par opération
            fautive. Vide si `VALIDE` ou pas encore vérifié.
        rapports_application: un `RapportOperation` par opération TENTÉE,
            dans l'ordre — rempli par `appliquer_plan()`.
    """

    operations: List[Operation]
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    statut: StatutPlan = StatutPlan.PROPOSE
    cree_le: str = field(default_factory=_maintenant)
    applique_le: Optional[str] = None
    annule_le: Optional[str] = None
    raisons_refus: List[str] = field(default_factory=list)
    rapports_application: List[RapportOperation] = field(default_factory=list)

    # --- Comptages, dans le vocabulaire du contrat headless d'AI File Sorter --
    # (entryCount/movedCount/renamedCount/skippedCount) — un statut machine-
    # lisible que le connecteur rend tel quel, mission §33 section C/D le
    # demande explicitement pour l'observabilité.

    @property
    def total(self) -> int:
        return len(self.operations)

    @property
    def deplaces(self) -> int:
        return sum(1 for r in self.rapports_application
                   if r.ok and r.operation.type is TypeOperation.DEPLACER)

    @property
    def copies(self) -> int:
        return sum(1 for r in self.rapports_application
                   if r.ok and r.operation.type is TypeOperation.COPIER)

    @property
    def supprimes(self) -> int:
        return sum(1 for r in self.rapports_application
                   if r.ok and r.operation.type is TypeOperation.SUPPRIMER)

    @property
    def dossiers_crees(self) -> int:
        return sum(1 for r in self.rapports_application
                   if r.ok and r.operation.type is TypeOperation.CREER_DOSSIER)

    @property
    def echecs(self) -> int:
        return sum(1 for r in self.rapports_application if not r.ok)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.identifiant, "statut": self.statut.value,
            "cree_le": self.cree_le, "applique_le": self.applique_le,
            "annule_le": self.annule_le,
            "operations": [o.to_dict() for o in self.operations],
            "raisons_refus": self.raisons_refus,
            "rapports_application": [r.to_dict() for r in self.rapports_application],
            "total": self.total, "deplaces": self.deplaces, "copies": self.copies,
            "supprimes": self.supprimes, "dossiers_crees": self.dossiers_crees,
            "echecs": self.echecs,
        }
