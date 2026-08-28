"""Chronometrer ce qui tourne vraiment, et dire `UNKNOWN` pour le reste.

La phase 7.1 declare des budgets. Ce sont des cibles : personne ne les a
chronometres. Ce module fournit de quoi les confronter au reel, avec une seule
regle qui commande toutes les autres.

**Une mesure absente ne devient jamais un chiffre.** Pas de zero par defaut, pas
de valeur plausible, pas de moyenne d'autre chose. Une scene qui n'a pas pu
tourner rapporte son etat et la raison ; elle n'occupe pas la ligne d'un
resultat.

**Quatre regles :**

1. **`MESURE` exige des secondes ; tout autre etat les refuse.** La construction
   echoue autrement — meme discipline que `ResultatAction`, ou un `SUCCESS` sans
   preuve ne se construit pas.

2. **Zero est une mesure, `None` est une absence.** Une operation trop rapide
   pour le chronometre a bien tourne ; une operation qui n'a pas tourne n'a pas
   de duree.

3. **Une scene non mesuree n'est ni dans le budget ni hors budget.** Son verdict
   est `NON_MESURE`. Comparer une absence a une cible fabrique une conclusion.

4. **Le rapport montre ce qui a manque.** Une ligne `UNKNOWN` reste dans le
   tableau : c'est elle qui dit ce que la machine ne sait pas encore faire.
"""
import inspect
import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence, Tuple

from core.execution.voies import Voie, budget_de

logger = logging.getLogger("usman.execution.mesures")

ETAT_MESURE = "MESURE"
ETAT_INDISPONIBLE = "INDISPONIBLE"
ETAT_NON_LANCE = "NON_LANCE"

VERDICT_DANS_LE_BUDGET = "DANS_LE_BUDGET"
VERDICT_HORS_BUDGET = "HORS_BUDGET"
VERDICT_NON_MESURE = "NON_MESURE"

#: Longueur maximale d'un detail d'erreur reporte. Un message d'exception peut
#: contenir une adresse complete, cle comprise : on garde de quoi diagnostiquer,
#: pas de quoi divulguer.
DETAIL_MAX = 120


@dataclass(frozen=True)
class Mesure:
    """Une scene chronometree, ou la raison pour laquelle elle ne l'a pas ete."""

    nom: str
    voie: Voie
    etat: str
    secondes: Optional[float] = None
    echantillons: Tuple[float, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if self.etat == ETAT_MESURE and self.secondes is None:
            raise ValueError(
                f"{self.nom} : une mesure sans duree n'est pas une mesure. "
                "Utiliser INDISPONIBLE et dire pourquoi."
            )
        if self.etat != ETAT_MESURE and self.secondes is not None:
            raise ValueError(
                f"{self.nom} : {self.etat} porte une duree de {self.secondes}. "
                "Une scene qui n'a pas tourne n'a pas de duree."
            )

    @property
    def verdict(self) -> str:
        """Dans le budget, hors budget, ou non mesure. Jamais deduit d'une absence."""
        if self.etat != ETAT_MESURE or self.secondes is None:
            return VERDICT_NON_MESURE
        cible = budget_de(self.voie).objectif_secondes
        return VERDICT_DANS_LE_BUDGET if self.secondes <= cible else VERDICT_HORS_BUDGET

    def rendre(self) -> str:
        """Une ligne de tableau. L'absence s'ecrit `UNKNOWN`, pas `0`."""
        if self.secondes is None:
            duree = "UNKNOWN"
        elif self.secondes < 1.0:
            duree = f"{self.secondes * 1000:.1f} ms"
        else:
            duree = f"{self.secondes:.2f} s"
        cible = f"{budget_de(self.voie).objectif_secondes:g} s"
        detail = f"  — {self.detail}" if self.detail else ""
        return f"{self.nom:<28} {self.voie.value:<9} {duree:>11}  cible {cible:>7}  {self.verdict}{detail}"


def _detail_de(erreur: BaseException) -> str:
    texte = f"{type(erreur).__name__}: {erreur}".replace("\n", " ")
    return texte[:DETAIL_MAX]


async def chronometrer(
    nom: str,
    voie: Voie,
    appel: Callable[[], Any],
    repetitions: int = 1,
) -> Mesure:
    """Fait tourner `appel` et rend sa duree, ou la raison de son absence.

    Accepte un appel synchrone comme asynchrone. Une exception n'est jamais
    propagee : elle devient un etat `INDISPONIBLE` avec sa raison, parce qu'une
    campagne de mesures ne doit pas s'arreter a la premiere scene impossible.

    Args:
        nom: le nom de la scene, tel qu'il apparaitra dans le rapport.
        voie: la voie dont le budget sert de cible.
        appel: ce qu'il faut chronometrer, sans argument.
        repetitions: combien de fois. La duree retenue est la **mediane** —
            une seule execution mesure autant le hasard que la machine.

    Returns:
        La mesure. `secondes` vaut `None` des que l'etat n'est pas `MESURE`.
    """
    if repetitions < 1:
        raise ValueError("Mesurer zero fois ne mesure rien.")

    durees: List[float] = []
    for _ in range(repetitions):
        depart = time.perf_counter()
        try:
            resultat = appel()
            if inspect.isawaitable(resultat):
                await resultat
        except Exception as erreur:  # noqa: BLE001 — une scene impossible est un etat
            logger.info("Scene %s indisponible : %s", nom, _detail_de(erreur))
            return Mesure(nom=nom, voie=voie, etat=ETAT_INDISPONIBLE,
                          detail=_detail_de(erreur))
        durees.append(time.perf_counter() - depart)

    return Mesure(
        nom=nom, voie=voie, etat=ETAT_MESURE,
        secondes=statistics.median(durees),
        echantillons=tuple(durees),
    )


def non_lancee(nom: str, voie: Voie, raison: str) -> Mesure:
    """Une scene qu'on n'a meme pas tentee, et pourquoi. Elle reste au rapport."""
    return Mesure(nom=nom, voie=voie, etat=ETAT_NON_LANCE, detail=raison)


@dataclass
class Rapport:
    """La campagne entiere, y compris ce qu'elle n'a pas pu mesurer."""

    mesures: List[Mesure] = field(default_factory=list)

    def ajouter(self, mesure: Mesure) -> None:
        self.mesures.append(mesure)

    @property
    def mesurees(self) -> List[Mesure]:
        return [m for m in self.mesures if m.etat == ETAT_MESURE]

    @property
    def manquantes(self) -> List[Mesure]:
        return [m for m in self.mesures if m.etat != ETAT_MESURE]

    @property
    def hors_budget(self) -> List[Mesure]:
        return [m for m in self.mesures if m.verdict == VERDICT_HORS_BUDGET]

    def rendre(self) -> str:
        """Le tableau complet. Les lignes manquantes y sont, marquees `UNKNOWN`."""
        if not self.mesures:
            return "Aucune scene declaree."
        lignes = [mesure.rendre() for mesure in self.mesures]
        lignes.append("")
        lignes.append(
            f"{len(self.mesurees)} mesuree(s), {len(self.manquantes)} UNKNOWN, "
            f"{len(self.hors_budget)} hors budget."
        )
        return "\n".join(lignes)


def resume_chiffre(mesures: Sequence[Mesure]) -> Optional[float]:
    """La mediane des scenes reellement mesurees. `None` s'il n'y en a aucune.

    Rendre `0.0` pour une campagne vide donnerait un chiffre a montrer la ou il
    n'y a rien a montrer.
    """
    durees = [m.secondes for m in mesures if m.secondes is not None]
    return statistics.median(durees) if durees else None
