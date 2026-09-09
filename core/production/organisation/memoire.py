"""Ce qu'un classement RÉUSSI apprend, dans la mémoire qui existe déjà.

Mission §19 : « AI File Sorter possède un cache et un système de
comportement appris... si ARENA possède déjà une mémoire, ne crée pas une
deuxième mémoire. » `MemoirePersonnelle` (`core/memory/personnelle.py`)
existe depuis la phase 6.1 — ce module n'en crée aucune deuxième, il y
écrit des souvenirs `PREFERENCE` quand un plan de classement a réellement
été appliqué avec succès.

**Ça ne modifie jamais le modèle.** Un souvenir `PREFERENCE` est relu au
prochain classement par l'agent qui consulte la mémoire avant de proposer
un plan — comme n'importe quel autre souvenir. Rien ici n'entraîne, ne
fine-tune, ni n'ajuste un poids.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.production.organisation.plan import Plan, TypeOperation

logger = logging.getLogger("usman.production.organisation.memoire")


def apprendre_du_plan(memoire_longue: Optional[Any], plan: Plan,
                      projet: Optional[str] = None) -> int:
    """Retient une préférence par déplacement/renommage réussi. Rend le
    nombre de souvenirs réellement écrits — jamais supposé.

    Best-effort : une mémoire absente ou en panne ne fait jamais échouer un
    classement déjà appliqué sur disque. Écrire ce qu'on a appris est un
    bonus, jamais une condition de succès.
    """
    if memoire_longue is None:
        return 0

    from core.memory.personnelle import Nature, TypeSouvenir

    ecrits = 0
    for rapport in plan.rapports_application:
        if not rapport.ok or rapport.operation.type is not TypeOperation.DEPLACER:
            continue
        operation = rapport.operation
        try:
            memoire_longue.retenir(
                contenu=f"Classement appliqué : « {operation.source} » -> "
                        f"« {operation.destination} »"
                        + (f" ({operation.raison})" if operation.raison else ""),
                type=TypeSouvenir.PROCEDURALE, nature=Nature.PREFERENCE,
                source="file_organization", projet=projet,
                metadonnees={"plan_id": plan.identifiant, "source": operation.source,
                            "destination": operation.destination},
            )
        except Exception as erreur:  # noqa: BLE001 — apprendre ne doit jamais casser un classement deja fait
            logger.warning("Souvenir de classement non ecrit (%s -> %s) : %s",
                           operation.source, operation.destination, erreur)
            continue
        ecrits += 1
    return ecrits
