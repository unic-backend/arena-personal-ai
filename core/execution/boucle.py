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

**Six regles, et la premiere commande les autres.**

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

6. **Les echecs s'accumulent, ils ne disparaissent pas.** Une etape qui a
   echoue laisse une trace : `echecs_cumules` porte, par nom d'etape, toutes
   les raisons d'echec vues depuis le debut. Le planificateur les relit a
   chaque tour — il ne peut plus reproposer en silence ce qui a deja echoue.
   C'est additif : aucun test existant ne change de comportement.

**Note d'implementation.** `echecs_cumules` sur chaque `Observation` est une
**copie profonde** de l'etat au moment du tour : chaque liste de raisons est
recreee. Sans cela, toutes les observations partageraient les memes listes, et
un echec survenu au tour 3 apparaitrait retroactivement dans l'observation du
tour 1 — c'est-a-dire n'importe ou.
"""
from __future__ import annotations

import inspect
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.execution.coordination import Coordination, Etape, Resultat, Trace
from core.observabilite.fil import (
    fil_courant,
    plan,
    souvenirs_lus,
    type_tache_courant,
)
from core.observabilite.plans import JournalDesPlans, PlanExecute

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
    #: Le planificateur a propose exactement les memes etapes que le tour
    #: precedent, sans que l'objectif soit atteint. Insister ne produirait
    #: pas autre chose que ce qu'on vient d'obtenir. Seulement pose quand
    #: `anti_repetition=True` : sans ce drapeau, la boucle garde son
    #: comportement historique et consomme son budget de tours.
    PLAN_REPETE = "REPEATED_PLAN"


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
    reelles d'echec, telles que `Coordination` les a gardees. Depuis
    l'ajout de `echecs_cumules`, un tour porte aussi la memoire des echecs
    anterieurs : le planificateur n'a pas a recalculer l'historique.
    """

    tour: int
    plan: List[str]
    reussies: List[str] = field(default_factory=list)
    echouees: List[Tuple[str, str]] = field(default_factory=list)
    abandonnees: List[str] = field(default_factory=list)
    atteint: bool = False
    pourquoi: str = ""
    #: Par nom d'etape, toutes les raisons d'echec vues depuis le debut,
    #: **ce tour inclus**. Un nom qui apparait 2 fois ou plus est une etape
    #: qui resiste : le planificateur devrait la reconsiderer autrement.
    #: Copie profonde au moment du tour — jamais une vue partagee.
    echecs_cumules: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"tour": self.tour, "plan": list(self.plan),
                             "reussies": list(self.reussies),
                             "echouees": [{"etape": n, "raison": r}
                                          for n, r in self.echouees],
                             "abandonnees": list(self.abandonnees),
                             "atteint": self.atteint, "pourquoi": self.pourquoi}
        if self.echecs_cumules:
            d["echecs_cumules"] = {nom: list(raisons)
                                   for nom, raisons in self.echecs_cumules.items()}
        return d

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
    #: L'identifiant de CETTE execution. Deux executions du meme objectif en ont
    #: deux differents : c'est ce qui permet de les distinguer quand la premiere
    #: a echoue.
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tours: List[Observation] = field(default_factory=list)
    etapes_consommees: int = 0
    #: `None` tant qu'aucun compteur d'outils n'est branche (regle 5).
    appels_outils: Optional[int] = None
    secondes: float = 0.0
    raison_d_arret: Optional[RaisonDArret] = None
    #: Ce que la derniere execution a produit, par nom d'etape.
    acquis: Dict[str, Any] = field(default_factory=dict)
    #: Par nom d'etape, la liste de toutes les raisons d'echec rencontrees
    #: (etapes `FAILED` seulement). Toujours alimente : ce n'est pas une
    #: option, c'est une memoire. La lire ne change rien pour les appelants
    #: qui ne s'y interessent pas.
    echecs_cumules: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def atteint(self) -> bool:
        return self.raison_d_arret is RaisonDArret.OBJECTIF_ATTEINT

    @property
    def replanifications(self) -> int:
        """Combien de fois le plan a ete refait. Zero = un seul plan."""
        return max(0, len(self.tours) - 1)

    @property
    def etapes_recalcitrantes(self) -> Dict[str, int]:
        """Etapes echouees 2 fois ou plus, avec le nombre d'echecs.

        Lecture seule : sert au diagnostic et a l'affichage. Le planificateur,
        lui, lit `echecs_cumules` en entier pour decider — un echec unique
        peut etre une panne transitoire, deux la meme chose commence a
        ressembler a une mauvaise idee.
        """
        return {nom: len(raisons) for nom, raisons in self.echecs_cumules.items()
                if len(raisons) >= 2}

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "plan_id": self.plan_id,
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
        if self.echecs_cumules:
            d["echecs_cumules"] = {nom: list(raisons)
                                   for nom, raisons in self.echecs_cumules.items()}
            d["etapes_recalcitrantes"] = self.etapes_recalcitrantes
        return d

    def rendre(self) -> str:
        lignes = [f"Objectif : {self.objectif}"]
        lignes += [o.rendre() for o in self.tours]
        raison = self.raison_d_arret.value if self.raison_d_arret else "SANS RAISON"
        lignes.append(
            f"Arret : {raison} — {self.etapes_consommees}/{self.budget.etapes_max} "
            f"etape(s), {len(self.tours)}/{self.budget.tours_max} tour(s), "
            f"{self.secondes:.1f}/{self.budget.secondes_max:.0f} s"
        )
        recalcitrantes = self.etapes_recalcitrantes
        if recalcitrantes:
            details = ", ".join(f"{nom} ({n}x)" for nom, n in recalcitrantes.items())
            lignes.append(f"Etapes recalcitrantes : {details}")
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
        parallelisme: Optional[int] = None,
        journal: Optional[JournalDesPlans] = None,
        anti_repetition: bool = False,
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
            parallelisme: si donne, les etapes d'un tour partent en parallele
                (borne a cette valeur) au lieu d'etre attendues une par une.
                Existe pour un appelant qui consultait DEJA en parallele :
                passer par la boucle ne doit pas serialiser ce qui ne l'etait
                pas — ce serait payer la replanification avec de la latence.
            journal: ou l'execution est enregistree. `None` = pas de trace.
            anti_repetition: si vrai, la boucle s'arrete des que le
                planificateur propose un plan dont les noms d'etapes sont
                identiques a ceux du tour precedent, alors que l'objectif
                n'etait pas atteint. **Opt-in** pour ne pas changer le
                comportement historique : la valeur par defaut reste
                `False`, et la boucle consomme son budget de tours comme
                avant.
        """
        if not (objectif or "").strip():
            raise ValueError("Une boucle sans objectif ne peut rien evaluer.")
        self.objectif = objectif
        self.planifier = planifier
        self.evaluer = evaluer
        self.budget = budget or Budget()
        self.observateur = observateur
        self.compteur_outils = compteur_outils
        if parallelisme is not None and parallelisme < 1:
            raise ValueError("Un parallelisme inferieur a 1 n'execute rien.")
        self.parallelisme = parallelisme
        #: Ou l'execution sera enregistree. `None` : la boucle tourne sans
        #: laisser de trace — c'est le cas d'un test ou d'un appel direct, et
        #: ce n'est pas une panne.
        self.journal = journal
        self.anti_repetition = anti_repetition
        #: Suivi de repetition : noms du dernier plan, et si l'objectif etait
        #: atteint a ce moment-la. Utilises uniquement quand `anti_repetition`
        #: est vrai. Toujours tenus a jour : coute une affectation.
        self._dernier_plan: Optional[Tuple[str, ...]] = None
        self._dernier_atteint: bool = False
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
        """Le passage OBLIGE de tout arret — donc le seul endroit ou enregistrer.

        La boucle ne sort jamais sans raison : chaque `return` du corps passe
        ici. Une ligne sans raison dans le journal des plans signalerait donc un
        chemin qui contourne cette methode, et c'est exactement ce qu'on veut
        pouvoir voir.
        """
        self.etat.secondes = time.perf_counter() - depart
        self.etat.raison_d_arret = raison
        logger.info("Boucle « %s » arretee : %s (%s etape(s), %s tour(s))",
                    self.objectif[:60], raison.value,
                    self.etat.etapes_consommees, len(self.etat.tours))
        self._enregistrer()
        return self.etat

    def _enregistrer(self) -> None:
        """Ecrit l'execution au journal des plans. Ne leve jamais.

        Avant le 13/09/2026, `raison_d_arret` finissait dans une ligne de
        journal applicatif — c'est-a-dire nulle part ou quelqu'un puisse la
        retrouver le lendemain. « Objectif atteint », « budget de tours
        epuise » et « plus de temps » se ressemblent vues de l'exterieur, et
        elles appellent trois gestes differents.
        """
        if self.journal is None:
            return
        self.journal.enregistrer(PlanExecute(
            plan_id=self.etat.plan_id,
            objectif=self.objectif,
            raison_d_arret=self.etat.raison_d_arret.value,
            atteint=self.etat.atteint,
            tours=len(self.etat.tours),
            etapes=self.etat.etapes_consommees,
            secondes=self.etat.secondes,
            requete=fil_courant(),
            type_tache=type_tache_courant(),
            # `None` quand aucun compteur n'etait branche : la regle 5 de cette
            # boucle. Ecrire `0` ferait lire « aucun outil appele » la ou la
            # verite est « personne n'a compte ».
            appels_outils=self.etat.appels_outils,
            souvenirs_consultes=souvenirs_lus(),
        ))

    async def executer(self) -> EtatBoucle:
        """Conduit la boucle jusqu'a une raison d'arret. N'en sort jamais sans."""
        with plan(self.etat.plan_id):
            return await self._conduire()

    def _memoriser_echecs(self, resultat: Resultat) -> None:
        """Ajoute au passe les echecs du tour qui vient de tourner.

        Seules les etapes `FAILED` (obligatoires et ratees) sont comptees :
        une etape `ABANDONNEE` etait facultative, et le fait qu'elle n'ait
        pas tourne n'est pas la meme information. Une etape `NON_ATTEINTE`
        n'a jamais ete essayee du tout.
        """
        for trace in resultat.traces:
            if trace.etat.value == "FAILED":
                self.etat.echecs_cumules.setdefault(trace.nom, []).append(
                    trace.raison or "sans raison"
                )

    def _copie_profonde_echecs(self) -> Dict[str, List[str]]:
        """Copie des echecs ou chaque liste est independante.

        `dict(...)` seul ne suffit pas : les listes seraient partagees, et un
        echec ajoute au tour N apparaitrait retroactivement dans l'observation
        du tour 1. Chaque observation doit voir l'historique tel qu'il etait
        a SON moment.
        """
        return {nom: list(raisons)
                for nom, raisons in self.etat.echecs_cumules.items()}

    async def _conduire(self) -> EtatBoucle:
        """Le corps de la boucle, sous le plan pose par `executer`."""
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

            # Regle 6 : anti-repetition (opt-in). Si le planificateur propose
            # exactement les memes noms d'etapes qu'au tour precedent, alors
            # que l'objectif n'etait pas atteint, insister n'apprendra rien de
            # plus — la boucle s'arrete et le dit.
            noms = tuple(e.nom for e in etapes)
            if (self.anti_repetition
                    and self._dernier_plan == noms
                    and not self._dernier_atteint):
                logger.info("Plan identique au tour precedent, sans succes : arret.")
                return self._arreter(RaisonDArret.PLAN_REPETE, depart)
            self._dernier_plan = noms

            # Regle 4 : un plan qui ne tient pas n'est pas execute a moitie.
            restantes = self.budget.etapes_max - self.etat.etapes_consommees
            if len(etapes) > restantes:
                return self._arreter(RaisonDArret.BUDGET_ETAPES, depart)

            numero = len(self.etat.tours) + 1
            coordination = Coordination(
                tache=f"{self.objectif} — tour {numero}",
                etapes=etapes, observateur=self.observateur,
            )
            resultat = await (
                coordination.executer_parallele(parallelisme=self.parallelisme)
                if self.parallelisme is not None else coordination.executer()
            )

            self.etat.etapes_consommees += len(etapes)
            self.etat.acquis = resultat.resultats

            # Regle 6 : les echecs s'accumulent AVANT qu'on evalue, pour que
            # l'observation du tour porte deja l'historique a jour.
            self._memoriser_echecs(resultat)

            atteint, pourquoi = self.evaluer(resultat, resultat.resultats)

            self.etat.tours.append(Observation(
                tour=numero,
                plan=[e.nom for e in etapes],
                reussies=[t.nom for t in resultat.traces if t.etat.value == "DONE"],
                echouees=[(t.nom, t.raison) for t in resultat.traces
                          if t.etat.value == "FAILED"],
                abandonnees=[t.nom for t in resultat.abandonnees],
                atteint=bool(atteint), pourquoi=str(pourquoi or ""),
                # Copie profonde : chaque observation voit l'historique tel
                # qu'il etait a SON moment, pas une vue partagee qui bouge
                # apres coup.
                echecs_cumules=self._copie_profonde_echecs(),
            ))
            self.etat.appels_outils = self._outils_consommes(outils_au_depart)
            self._dernier_atteint = bool(atteint)

            if atteint:
                return self._arreter(RaisonDArret.OBJECTIF_ATTEINT, depart)