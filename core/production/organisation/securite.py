"""Un plan n'est validé que si chaque opération, une par une, tient.

Contrairement à `tools/atelier/atelier.py` (DEC-0038 : aucune garde, c'est la
décision du propriétaire pour SES mains directes sur SA machine), cette
capacité est neuve — elle n'hérite d'aucune exemption. Ses plans restent
DÉLIBÉRÉMENT confinés au dossier qu'on lui a demandé d'organiser : mission
§14, « ne donne pas à un agent la capacité de déplacer un fichier
arbitraire n'importe où sans contrôle ».

**Quatre règles**, chacune sabotage-vérifiée dans
`tests/core/test_connecteur_file_organization.py` :

1. Une source qui n'existe pas refuse le plan entier — pas seulement
   l'opération fautive : un plan partiellement applicable induirait en
   erreur sur ce qui va réellement se passer.
2. Une destination hors du dossier confié refuse le plan.
3. Une destination qui existe déjà refuse, sauf si `ecraser=True` est
   explicitement demandé opération par opération — jamais un défaut.
4. Un chemin sensible (`.ssh`, `.env`, une clé privée...) refuse, en
   source comme en destination — même liste que `core/connectors/
   gitingest.py` et `core/production/conversion/securite.py`.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from core.production.organisation.plan import Operation, TypeOperation

#: Même liste que gitingest.py / conversion/securite.py — le même risque,
#: recopié plutôt que partagé entre trois connecteurs indépendants.
SEGMENTS_INTERDITS = frozenset({
    ".ssh", ".aws", ".gnupg", ".git-credentials", ".netrc",
    "id_rsa", "id_ed25519", "id_ecdsa",
})
FICHIERS_INTERDITS = frozenset({".env", "credentials.json", "secrets.json"})

#: Un plan plus grand que ça n'est pas une organisation raisonnable pour un
#: seul appel — mission §6, même plafond d'esprit que le lot de conversion.
OPERATIONS_MAX = 500


def _segment_sensible(chemin: Path) -> Optional[str]:
    segments_bas = {p.lower() for p in chemin.parts}
    trouve = SEGMENTS_INTERDITS & segments_bas
    if trouve:
        return sorted(trouve)[0]
    if chemin.name.lower() in FICHIERS_INTERDITS:
        return chemin.name
    return None


def _resoudre_dans(racine: Path, chemin_relatif: str) -> Optional[Path]:
    """Le chemin résolu s'il reste sous `racine`, sinon `None`."""
    try:
        resolu = (racine / chemin_relatif).resolve()
        racine_resolue = racine.resolve()
    except OSError:
        return None
    if resolu != racine_resolue and racine_resolue not in resolu.parents:
        return None
    return resolu


def valider_plan(racine: Path, operations: List[Operation],
                 ecrasements_autorises: Optional[set] = None) -> Tuple[bool, List[str]]:
    """`(True, [])` si chaque opération tient ; `(False, raisons)` sinon.

    Args:
        racine: le dossier confié — toute source/destination doit y rester.
        operations: le plan proposé, tel quel.
        ecrasements_autorises: indices (dans `operations`) où une
            destination déjà existante est explicitement acceptée.
    """
    ecrasements_autorises = ecrasements_autorises or set()
    raisons: List[str] = []

    if not operations:
        return False, ["le plan est vide : rien à valider"]
    if len(operations) > OPERATIONS_MAX:
        raisons.append(f"{len(operations)} opérations demandées, plafond {OPERATIONS_MAX}")

    destinations_vues: dict = {}

    for i, op in enumerate(operations):
        source_resolue = _resoudre_dans(racine, op.source)
        if source_resolue is None:
            raisons.append(f"opération {i} : source hors du dossier confié ({op.source})")
            continue
        segment = _segment_sensible(source_resolue)
        if segment:
            raisons.append(f"opération {i} : chemin sensible en source (« {segment} »)")
            continue
        if op.type is not TypeOperation.CREER_DOSSIER and not source_resolue.exists():
            raisons.append(f"opération {i} : source introuvable ({op.source})")
            continue

        if op.type in (TypeOperation.SUPPRIMER, TypeOperation.CREER_DOSSIER):
            continue  # ni l'un ni l'autre n'a de destination a verifier

        if not op.destination:
            raisons.append(f"opération {i} : destination manquante pour {op.type.value}")
            continue

        destination_resolue = _resoudre_dans(racine, op.destination)
        if destination_resolue is None:
            raisons.append(f"opération {i} : destination hors du dossier confié ({op.destination})")
            continue
        segment = _segment_sensible(destination_resolue)
        if segment:
            raisons.append(f"opération {i} : chemin sensible en destination (« {segment} »)")
            continue

        if str(destination_resolue) in destinations_vues:
            autre = destinations_vues[str(destination_resolue)]
            raisons.append(f"opérations {autre} et {i} : même destination ({op.destination})")
        destinations_vues[str(destination_resolue)] = i

        if (op.type in (TypeOperation.DEPLACER, TypeOperation.COPIER)
                and destination_resolue.exists() and i not in ecrasements_autorises):
            raisons.append(f"opération {i} : la destination existe déjà ({op.destination}) — "
                           f"écrasement non autorisé explicitement")

    return (len(raisons) == 0), raisons
