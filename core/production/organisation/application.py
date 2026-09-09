"""Appliquer un plan déjà validé, et pouvoir revenir en arrière.

Toute mutation passe par `Atelier` — jamais un accès filesystem parallèle.
Ce module ne décide rien : il exécute, dans l'ordre, ce qu'un plan
`VALIDE` contient, et construit au passage de quoi l'annuler.

**Ce qui N'EST PAS réversible ici, et pourquoi** : `SUPPRIMER` n'a pas
d'annulation — un fichier réellement effacé du disque ne revient pas. Le
connecteur (`core/connectors/file_organization.py`) le sait et exige une
confirmation séparée, à risque HIGH, spécifiquement pour cette opération.
"""
from __future__ import annotations

import logging
from typing import Any, List

from core.production.organisation.plan import (
    Operation,
    Plan,
    RapportOperation,
    StatutPlan,
    TypeOperation,
)

logger = logging.getLogger("usman.production.organisation.application")


def appliquer_plan(atelier: Any, plan: Plan) -> Plan:
    """Exécute un plan `VALIDE`, opération par opération, dans l'ordre.

    Une opération qui échoue n'arrête pas les suivantes — chacune est
    indépendante, et le rapport dit précisément laquelle a raté. Le plan
    passe à `ECHEC` si au moins une opération a échoué, `APPLIQUE` sinon —
    jamais annoncé réussi en bloc quand une partie a raté (même discipline
    que `Statut.PARTIEL` ailleurs dans ARENA).
    """
    if plan.statut is not StatutPlan.VALIDE:
        raise ValueError(f"Un plan {plan.statut.value} ne peut pas être appliqué "
                         f"— seul un plan VALIDATED le peut.")

    for operation in plan.operations:
        rapport = _appliquer_une(atelier, operation)
        plan.rapports_application.append(rapport)

    from datetime import datetime, timezone
    plan.applique_le = datetime.now(timezone.utc).isoformat(timespec="seconds")
    plan.statut = StatutPlan.ECHEC if plan.echecs else StatutPlan.APPLIQUE
    return plan


def _appliquer_une(atelier: Any, operation: Operation) -> RapportOperation:
    if operation.type is TypeOperation.DEPLACER:
        resultat = atelier.deplacer(operation.source, operation.destination)
    elif operation.type is TypeOperation.COPIER:
        resultat = atelier.copier(operation.source, operation.destination)
    elif operation.type is TypeOperation.CREER_DOSSIER:
        resultat = atelier.creer_dossier(operation.source)
    elif operation.type is TypeOperation.SUPPRIMER:
        resultat = atelier.supprimer(operation.source)
    else:  # pragma: no cover — TypeOperation est fermé, inatteignable en pratique
        return RapportOperation(operation, False, f"type d'opération inconnu : {operation.type}")

    return RapportOperation(operation, resultat.ok, resultat.message)


def annuler_plan(atelier: Any, plan: Plan) -> Plan:
    """Rejoue l'inverse de chaque opération APPLIQUÉE avec succès, dans
    l'ordre INVERSE (la dernière appliquée est la première défaite — comme
    une pile, pour ne jamais tenter de défaire une opération dont la
    précédente dépendait d'un état qu'on vient déjà de changer).

    `SUPPRIMER` n'a pas d'inverse : ces opérations sont ignorées ici — le
    connecteur les signale séparément comme irréversibles.
    """
    if plan.statut not in (StatutPlan.APPLIQUE, StatutPlan.ECHEC):
        raise ValueError(f"Un plan {plan.statut.value} n'a rien à annuler "
                         f"— seul un plan APPLIED ou FAILED (partiellement appliqué) le peut.")

    rapports_annulation: List[RapportOperation] = []
    for rapport in reversed(plan.rapports_application):
        if not rapport.ok:
            continue  # jamais tente : rien a defaire
        rapports_annulation.append(_annuler_une(atelier, rapport.operation))

    from datetime import datetime, timezone
    plan.annule_le = datetime.now(timezone.utc).isoformat(timespec="seconds")
    plan.statut = StatutPlan.ANNULE
    plan.rapports_application = rapports_annulation
    return plan


def _annuler_une(atelier: Any, operation: Operation) -> RapportOperation:
    """Défait UNE opération déjà appliquée avec succès.

    Pas un aller-retour générique par `Operation` inversée : `CREER_DOSSIER`
    n'a pas de véritable inverse dans le vocabulaire fermé de
    `TypeOperation` (son inverse est « retirer un dossier VIDE », distinct
    de `SUPPRIMER`, qui refuse tout dossier — voir `Atelier.
    supprimer_dossier_vide()`) ; le représenter en cas spécial ici est plus
    honnête qu'un cinquième type d'opération qu'aucun plan ne proposerait
    jamais lui-même.
    """
    if operation.type is TypeOperation.DEPLACER:
        resultat = atelier.deplacer(operation.destination, operation.source)
        return RapportOperation(operation, resultat.ok, resultat.message)
    if operation.type is TypeOperation.COPIER:
        resultat = atelier.supprimer(operation.destination)
        return RapportOperation(operation, resultat.ok, resultat.message)
    if operation.type is TypeOperation.CREER_DOSSIER:
        resultat = atelier.supprimer_dossier_vide(operation.source)
        return RapportOperation(operation, resultat.ok, resultat.message)
    # SUPPRIMER : jamais reversible, un fichier efface ne revient pas.
    return RapportOperation(
        operation, False,
        f"{operation.type.value} n'est pas réversible — ignoré à l'annulation.")
