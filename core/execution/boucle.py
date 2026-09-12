"""Un plan qui se revise apres observation, et qui s'arrete toujours.

`core/execution/coordination.py` conduit une liste d'etapes **fixe** : elle
retente, elle depend, elle verifie, elle garde l'etat. Ce qui lui manque est
d'un autre ordre — **le plan lui-meme ne change jamais**. Mesure du 12/09/2026
(`docs/audits/audit_phase0_2026-09-12.md`, section D) :
`ReasoningEngine.solve_complex_task` produit son plan une fois et ne le revise
pas ; « replan » n'apparaissait dans aucun module du coeur.

Ce module ajoute la seule chose qui manquait : **apres avoir observe, on peut
planifier autrement**. Il ne remplace ni `Coordination`, ni un agent : il les
conduit.

**Cinq regles, et la premiere commande les autres.**

1. **L'etat vit en Python, jamais dans du texte genere.** Un modele peut
   *proposer* des etapes ; ce sont des objets `Etape` qui s'executent, et c'est
   `EtatBoucle` qui dit ce qui a eu lieu. Une boucle dont l'etat vit dans la
   reponse du modele ne boucle pas : elle raconte qu'elle boucle.

2. **La boucle s'arrete toujours, et dit pourquoi.** Chaque sortie porte une
   `RaisonDArret`. Il n'existe aucun chemin qui sorte sans raison — c'est ce
   que `objectif_atteint` seul ne garantirait pas.

3. **Un budget depasse arrete avant d'agir, pas apres.** Le temps et les tours
   sont verifies AVANT de planifier, les etapes AVANT d'executer. Constater le
   depassement apres coup, c'est l'avoir laisse se produire.

4. **Un plan qui ne tient pas dans le budget n'est pas execute a moitie.** Un
   demi-plan n'est pas le plan propose : on s'arrete sur `BUDGET_ETAPES` en le
   disant, plutot que de rendre un resultat partiel qui aurait l'air complet.

5. **Ce qui n'a pas ete compte vaut `None`, jamais zero.** Sans compteur
   d'outils branche, `appels_outils` reste `None` : « aucun appel » et « je ne
   compte pas » sont deux etats differents.
"""
from __future__ import annotations

import inspect
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.execution.coordination import Coordination, Etape, Resultat, Trace

logger = logging.getLogger("usman.execution.boucle")


class RaisonDArret(str, Enum):
    """Pourquoi la boucle s'est arretee. Toujours renseignee."""

    OBJECTIF_ATTEINT = "GOAL_REACHED"
    #: Le planificateur ne propose plus rien : il n'a pas d'autre idee.
    PLAN_VIDE = "EMPTY_PLAN"
    #: Le planificateur a leve. La boucle ne se casse pas avec lui.
    PLANIFICATION_EN_ECHEC = "PLANNING_FAILED"
    BUDGET_TOURS = "REPLAN_BUDGET"
    BUDGET_ETAPES = "STEP_BUDGET"
    BUDGET_TEMPS = "TIME_BUDGET"
    BUDGET_OUTILS = "TOOL_BUDGET"


@dataclass
class Budget:
    """Ce que la boucle s'autorise. Aucune valeur n'est illimitee.

    Ecrit plutot que devine : une boucle qui replanifie sans plafond est une
    boucle infinie qui n'a pas encore eu l'occasion de le montrer.
    """

    #: Nombre total d'etapes executees, tous tours confondus.
    etapes_max: int = 12
    #: Nombre de PLANS. 1 = le plan initial, sans aucune replanification.
    tours_max: int = 4
    secondes_max: float = 120.0
    #: `None` = pas de plafond d'outils, et alors rien n'est compte.
    appels_outils_max: Optional[int] = None

    def __post_init__(self) -> None:
        if self.etapes_max < 1:
            raise ValueError("Un budget de zero etape n'execute rien.")
        if self.tours_max < 1:
            raise ValueError("Un budget de zero tour ne planifie jamais.")
        if self.secondes_max <= 0:
            raise ValueError("Un budget de temps nul n'attend rien.")
        if self.appels_outils_max is not None and self.appels_outils_max < 0:
            raise ValueError("Un plafond d'appels d'outils negatif n'a pas de sens.")

    def to_dict(self) -> Dict[str, Any]:
        return {"etapes_max": self.etapes_max, "tours_max": self.tours_max,
                "secondes_max": self.secondes_max,
                "appels_outils_max": self.appels_outils_max}


@dataclass
class Observation:
    """Ce qu'un tour a appris — c'est ce que le replanificateur relit.

    Ce n'est pas un resume redige : ce sont les noms des etapes et les raisons
    reelles d'echec, telles que `Coordination` les a gardees.
    """

    tour: int
    plan: List[str]
    reussies: List[str] = field(default_factory=list)
    echouees: List[Tuple[str, str]] = field(default_factory=list)
    abandonnees: List[str] = field(default_factory=list)
    atteint: bool = False
    pourquoi: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"tour": self.tour, "plan": list(self.plan),
                "reussies": list(self.reussies),
                "echouees": [{"etape": n, "raison": r} for n, r in self.echouees],
                "abandonnees": list(self.abandonnees),
                "atteint": self.atteint, "pourquoi": self.pourquoi}

    def rendre(self) -> str:
        lignes = [f"tour {self.tour} — plan : {', '.join(self.plan) or '(vide)'}"]
        if self.reussies:
            lignes.append(f"  reussies : {', '.join(self.reussies)}")
        for nom, raison in self.echouees:
            lignes.append(f"  echouee  : {nom} — {raison}")
        if self.abandonnees:
            lignes.append(f"  abandonnees : {', '.join(self.abandonnees)}")
        lignes.append(f"  objectif atteint : {'oui' if self.atteint else 'non'}"
                      + (f" — {self.pourquoi}" if self.pourquoi else ""))
        return "\n".join(lignes)


@dataclass
class EtatBoucle:
    """L'etat complet de la boucle. Rien ici n'est deduit apres coup."""

    objectif: str
    budget: Budget
    tours: List[Observation] = field(default_factory=list)
    etapes_consommees: int = 0
    #: `None` tant qu'aucun compteur d'outils n'est branche (regle 5).
    appels_outils: Optional[int] = None
    secondes: float = 0.0
    raison_d_arret: Optional[RaisonDArret] = None
    #: Ce que la derniere execution a produit, par nom d'etape.
    acquis: Dict[str, Any] = field(default_factory=dict)

    @property
    def atteint(self) -> bool:
        return self.raison_d_arret is RaisonDArret.OBJECTIF_ATTEINT

    @property
    def replanifications(self) -> int:
        """Combien de fois le plan a ete refait. Zero = un seul plan."""
        return max(0, len(self.tours) - 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objectif": self.objectif,
            "atteint": self.atteint,
            "raison_d_arret": self.raison_d_arret.value if self.raison_d_arret else None,
            "tours": [o.to_dict() for o in self.tours],
            "replanifications": self.replanifications,
            "etapes_consommees": self.etapes_consommees,
            "appels_outils": self.appels_outils,
            "secondes": round(self.secondes, 3),
            "budget": self.budget.to_dict(),
        }

    def rendre(self) -> str:
        lignes = [f"Objectif : {self.objectif}"]
        lignes += [o.rendre() for o in self.tours]
        raison = self.raison_d_arret.value if self.raison_d_arret else "SANS RAISON"
        lignes.append(
            f"Arret : {raison} — {self.etapes_consommees}/{self.budget.etapes_max} "
            f"etape(s), {len(self.tours)}/{self.budget.tours_max} tour(s), "
            f"{self.secondes:.1f}/{self.budget.secondes_max:.0f} s"
        )
        return "\n".join(lignes)


#: Ce qu'un planificateur rend : les etapes du prochain tour. Une liste vide
#: est une reponse valable — « je n'ai pas d'autre idee » — et arrete la boucle.
Planificateur = Callable[[str, List[Observation]], Sequence[Etape]]

#: Ce qu'un evaluateur rend : l'objectif est-il atteint, et pourquoi on le dit.
#: Deterministe : une phrase de modele n'est pas une evaluation.
Evaluateur = Callable[[Resultat, Dict[str, Any]], Tuple[bool, str]]


class BoucleAgentique:
    """Planifie, execute, observe, evalue, replanifie — et s'arrete.

    Elle ne connait ni modele ni outil : l'appelant fournit `planifier` (qui
    peut interroger un modele) et `evaluer` (qui ne doit pas). C'est ce qui
    garde la regle 1 : le modele propose, le Python dispose.
    """

    def __init__(
        self,
        objectif: str,
        planifier: Planificateur,
        evaluer: Evaluateur,
        budget: Optional[Budget] = None,
        observateur: Optional[Callable[[Trace], None]] = None,
        compteur_outils: Optional[Callable[[], int]] = None,
    ) -> None:
        """
        Args:
            objectif: ce qu'on cherche a obtenir, en clair.
            planifier: rend les etapes du prochain tour, en voyant les tours
                precedents. Peut etre asynchrone.
            evaluer: dit si l'objectif est atteint, a partir du resultat reel.
            budget: les plafonds. Ceux par defaut si absent.
            observateur: relaye les changements d'etat de chaque etape.
            compteur_outils: lit le compteur REEL d'appels d'outils. Sans lui,
                `appels_outils` reste `None` et le plafond ne s'applique pas.
        """
        if not (objectif or "").strip():
            raise ValueError("Une boucle sans objectif ne peut rien evaluer.")
        self.objectif = objectif
        self.planifier = planifier
        self.evaluer = evaluer
        self.budget = budget or Budget()
        self.observateur = observateur
        self.compteur_outils = compteur_outils
        self.etat = EtatBoucle(objectif=objectif, budget=self.budget)

    def _outils_consommes(self, depart: Optional[int]) -> Optional[int]:
        """Combien d'appels d'outils depuis le depart, ou None si non compte."""
        if self.compteur_outils is None or depart is None:
            return None
        try:
            return max(0, self.compteur_outils() - depart)
        except Exception as erreur:  # noqa: BLE001 — un compteur casse n'arrete rien
            logger.debug("Compteur d'outils illisible : %s", erreur)
            return None

    def _arreter(self, raison: RaisonDArret, depart: float) -> EtatBoucle:
        self.etat.secondes = time.perf_counter() - depart
        self.etat.raison_d_arret = raison
        logger.info("Boucle « %s » arretee : %s (%s etape(s), %s tour(s))",
                    self.objectif[:60], raison.value,
                    self.etat.etapes_consommees, len(self.etat.tours))
        return self.etat

    async def executer(self) -> EtatBoucle:
        """Conduit la boucle jusqu'a une raison d'arret. N'en sort jamais sans."""
        depart = time.perf_counter()
        outils_au_depart: Optional[int] = None
        if self.compteur_outils is not None:
            try:
                outils_au_depart = self.compteur_outils()
            except Exception as erreur:  # noqa: BLE001
                logger.debug("Compteur d'outils illisible au depart : %s", erreur)

        while True:
            self.etat.appels_outils = self._outils_consommes(outils_au_depart)

            # Regle 3 : les plafonds se verifient AVANT d'agir.
            if len(self.etat.tours) >= self.budget.tours_max:
                return self._arreter(RaisonDArret.BUDGET_TOURS, depart)
            if time.perf_counter() - depart >= self.budget.secondes_max:
                return self._arreter(RaisonDArret.BUDGET_TEMPS, depart)
            if (self.budget.appels_outils_max is not None
                    and self.etat.appels_outils is not None
                    and self.etat.appels_outils >= self.budget.appels_outils_max):
                return self._arreter(RaisonDArret.BUDGET_OUTILS, depart)

            try:
                propose = self.planifier(self.objectif, list(self.etat.tours))
                if inspect.isawaitable(propose):
                    propose = await propose
            except Exception as erreur:  # noqa: BLE001 — un planificateur casse
                logger.warning("Planification en echec : %s", erreur)      # n'emporte
                return self._arreter(RaisonDArret.PLANIFICATION_EN_ECHEC, depart)  # pas la boucle

            etapes = list(propose or [])
            if not etapes:
                return self._arreter(RaisonDArret.PLAN_VIDE, depart)

            # Regle 4 : un plan qui ne tient pas n'est pas execute a moitie.
            restantes = self.budget.etapes_max - self.etat.etapes_consommees
            if len(etapes) > restantes:
                return self._arreter(RaisonDArret.BUDGET_ETAPES, depart)

            numero = len(self.etat.tours) + 1
            resultat = await Coordination(
                tache=f"{self.objectif} — tour {numero}",
                etapes=etapes, observateur=self.observateur,
            ).executer()

            self.etat.etapes_consommees += len(etapes)
            self.etat.acquis = resultat.resultats
            atteint, pourquoi = self.evaluer(resultat, resultat.resultats)

            self.etat.tours.append(Observation(
                tour=numero,
                plan=[e.nom for e in etapes],
                reussies=[t.nom for t in resultat.traces if t.etat.value == "DONE"],
                echouees=[(t.nom, t.raison) for t in resultat.traces
                          if t.etat.value == "FAILED"],
                abandonnees=[t.nom for t in resultat.abandonnees],
                atteint=bool(atteint), pourquoi=str(pourquoi or ""),
            ))
            self.etat.appels_outils = self._outils_consommes(outils_au_depart)

            if atteint:
                return self._arreter(RaisonDArret.OBJECTIF_ATTEINT, depart)
