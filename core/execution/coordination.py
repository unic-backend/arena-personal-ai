"""Conduire une tache en plusieurs etapes sans perdre le fil.

ARENA savait deja faire tourner un travail long sans bloquer le chat
(`core/execution/travaux.py`), mesurer ce qu'une reponse coute
(`core/execution/mesures.py`) et choisir un fournisseur qui replie
(`core/models/routeur.py`). Ce qui manquait est entre les deux : **une tache
qui a plusieurs etapes, dont certaines echouent, et qui doit continuer quand
meme en sachant ou elle en est**.

Sans cela, une etape ratee laisse le reste de la chaine dans le flou : on ne
sait plus ce qui a tourne, ce qui a echoue, ni ce qui a ete abandonne. Le
raisonnement d'ARENA le faisait deja — plan, calcul, synthese — mais sans etat,
sans reprise, et sans verification.

**Six regles :**

1. **Chaque etat correspond a une operation reelle.** `EN_COURS` s'affiche
   pendant qu'une etape tourne, pas avant. Un etat invente serait pire que pas
   d'etat du tout.

2. **La reprise est bornee.** Une etape se retente un nombre de fois **ecrit**,
   avec une attente croissante. Retenter sans fin transforme une panne en
   boucle.

3. **Une etape facultative qui echoue n'arrete pas la tache.** Elle est marquee
   `ABANDONNEE`, la raison est gardee, et la suite continue. C'est ce qui
   permet a un calcul impossible de ne pas emporter la reponse avec lui.

4. **Une etape obligatoire qui echoue arrete la tache**, et l'etat dit
   exactement ou. On ne rend pas un resultat partiel en le presentant comme
   complet.

5. **La verification est une etape, pas une supposition.** Une etape peut
   declarer comment on sait qu'elle a reussi ; sans ce controle, « ca n'a pas
   leve » est tout ce qu'on peut affirmer, et c'est ce qui sera dit.

6. **Rien n'est perdu.** Tentatives, durees, resultats intermediaires, raisons
   d'echec : tout reste dans la trace, y compris pour les etapes abandonnees.
"""
import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("usman.execution.coordination")

#: Longueur maximale d'une raison conservee. Un message d'exception peut
#: transporter une adresse complete : on garde de quoi diagnostiquer.
RAISON_MAX = 200

#: Attente entre deux tentatives, doublee a chaque fois. Assez pour laisser
#: passer une panne breve, assez peu pour ne pas faire attendre une reponse.
ATTENTE_INITIALE = 0.5
ATTENTE_MAX = 8.0


class EtatEtape(str, Enum):
    """Les six etats d'une etape. Aucun n'est deduit : chacun est ecrit."""

    EN_ATTENTE = "PENDING"
    EN_COURS = "RUNNING"
    REUSSIE = "DONE"
    ECHOUEE = "FAILED"          # obligatoire, et elle a echoue : la tache s'arrete
    ABANDONNEE = "SKIPPED"      # facultative, et elle a echoue : la tache continue
    NON_ATTEINTE = "NOT_REACHED"  # une etape avant elle a arrete la tache


#: Ce qu'une verification rend : est-ce reussi, et pourquoi on le dit.
Verification = Callable[[Any], Tuple[bool, str]]


@dataclass
class Etape:
    """Une etape de la tache : ce qu'elle fait, et ce qu'elle s'autorise."""

    nom: str
    appel: Callable[..., Any]
    #: Combien de fois au maximum. 1 = aucune reprise.
    essais_max: int = 1
    #: Une etape facultative qui echoue n'arrete pas la tache.
    facultative: bool = False
    #: Comment on sait qu'elle a reussi. Sans elle, « ca n'a pas leve ».
    verifier: Optional[Verification] = None
    #: Ce qu'elle attend du resultat des etapes precedentes.
    depend_de: Tuple[str, ...] = ()
    #: Un groupe de ressource partagee (ex: "gpu_local") pour
    #: `executer_parallele()` : deux etapes du meme groupe ne tournent
    #: jamais en meme temps, meme si `depend_de` le permettrait. `None` =
    #: seule la limite globale de parallelisme s'applique. Sert a coder une
    #: contrainte materielle reelle (un seul GPU physique), jamais devinee
    #: par l'executeur lui-meme.
    ressource: Optional[str] = None

    def __post_init__(self) -> None:
        if self.essais_max < 1:
            raise ValueError(f"{self.nom} : une etape qui ne s'execute jamais "
                             "n'est pas une etape.")


@dataclass
class Trace:
    """Ce qu'une etape a reellement fait. Gardee meme quand elle a echoue."""

    nom: str
    etat: EtatEtape = EtatEtape.EN_ATTENTE
    tentatives: int = 0
    secondes: Optional[float] = None
    resultat: Any = None
    raison: str = ""
    verifiee: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"etape": self.nom, "etat": self.etat.value,
                "tentatives": self.tentatives, "secondes": self.secondes,
                "raison": self.raison, "verifiee": self.verifiee}


@dataclass
class Resultat:
    """L'etat complet de la tache : ce qui a tourne, ce qui a manque."""

    tache: str
    traces: List[Trace] = field(default_factory=list)
    aboutie: bool = False
    arretee_a: str = ""

    @property
    def resultats(self) -> Dict[str, Any]:
        """Ce que chaque etape reussie a produit, par nom."""
        return {trace.nom: trace.resultat for trace in self.traces
                if trace.etat is EtatEtape.REUSSIE}

    @property
    def abandonnees(self) -> List[Trace]:
        return [t for t in self.traces if t.etat is EtatEtape.ABANDONNEE]

    def trace_de(self, nom: str) -> Optional[Trace]:
        return next((t for t in self.traces if t.nom == nom), None)

    def rendre(self) -> str:
        """L'etat lisible. Ce qui a ete abandonne y figure, c'est le principal."""
        lignes = [f"{trace.nom} : {trace.etat.value}"
                  + (f" ({trace.tentatives} tentative(s))" if trace.tentatives > 1 else "")
                  + (f" — {trace.raison}" if trace.raison else "")
                  for trace in self.traces]
        if self.aboutie:
            lignes.append(f"Tache « {self.tache} » aboutie.")
        else:
            lignes.append(f"Tache « {self.tache} » arretee a : {self.arretee_a}.")
        return "\n".join(lignes)

    def to_dict(self) -> Dict[str, Any]:
        return {"tache": self.tache, "aboutie": self.aboutie,
                "arretee_a": self.arretee_a,
                "etapes": [trace.to_dict() for trace in self.traces],
                "abandonnees": [t.nom for t in self.abandonnees]}


def _raison(erreur: BaseException) -> str:
    return f"{type(erreur).__name__}: {erreur}".replace("\n", " ")[:RAISON_MAX]


class Coordination:
    """Fait tourner des etapes dans l'ordre, et garde l'etat de la tache.

    L'appelant peut observer la progression pendant l'execution : `resultat`
    porte l'etat courant, et chaque trace change au moment ou l'operation a
    lieu — jamais avant.
    """

    def __init__(self, tache: str, etapes: List[Etape],
                 observateur: Optional[Callable[[Trace], None]] = None) -> None:
        if not etapes:
            raise ValueError("Une tache sans etape n'est pas une tache.")
        self.tache = tache
        self.etapes = etapes
        # Appele a chaque changement d'etat : c'est ce qui alimente l'affichage
        # d'activite sans que celui-ci ait a deviner ou on en est.
        self.observateur = observateur
        self.resultat = Resultat(tache=tache,
                                 traces=[Trace(nom=etape.nom) for etape in etapes])

    def _signaler(self, trace: Trace) -> None:
        if self.observateur is None:
            return
        try:
            self.observateur(trace)
        except Exception as erreur:  # noqa: BLE001 — un afficheur casse n'arrete rien
            logger.debug("Observateur en echec : %s", _raison(erreur))

    async def _tenter(self, etape: Etape, trace: Trace,
                      acquis: Dict[str, Any]) -> bool:
        """Execute une etape, avec ses reprises. Rend vrai si elle a reussi."""
        attente = ATTENTE_INITIALE
        for tentative in range(1, etape.essais_max + 1):
            trace.tentatives = tentative
            depart = time.perf_counter()
            try:
                sortie = etape.appel(acquis) if _prend_acquis(etape.appel) else etape.appel()
                if inspect.isawaitable(sortie):
                    sortie = await sortie
            except Exception as erreur:  # noqa: BLE001 — un echec est un etat
                trace.raison = _raison(erreur)
                trace.secondes = time.perf_counter() - depart
                logger.info("Etape %s, tentative %s : %s", etape.nom, tentative,
                            trace.raison)
                if tentative < etape.essais_max:
                    await asyncio.sleep(min(attente, ATTENTE_MAX))
                    attente *= 2
                continue

            trace.secondes = time.perf_counter() - depart
            trace.resultat = sortie

            if etape.verifier is None:
                # Sans controle declare, tout ce qu'on peut affirmer est que
                # l'appel n'a pas leve. `verifiee` reste `None`, pas `True`.
                return True

            ok, pourquoi = etape.verifier(sortie)
            trace.verifiee = bool(ok)
            if ok:
                return True
            trace.raison = pourquoi or "verification echouee"
            if tentative < etape.essais_max:
                await asyncio.sleep(min(attente, ATTENTE_MAX))
                attente *= 2
        return False

    async def executer(self) -> Resultat:
        """Fait tourner la tache. Rend l'etat complet, abouti ou non."""
        acquis: Dict[str, Any] = {}

        for etape, trace in zip(self.etapes, self.resultat.traces, strict=True):
            manquantes = [nom for nom in etape.depend_de if nom not in acquis]
            if manquantes:
                # Ce dont elle a besoin n'a pas ete produit : on ne la lance pas
                # dans le vide.
                trace.etat = (EtatEtape.ABANDONNEE if etape.facultative
                              else EtatEtape.ECHOUEE)
                trace.raison = f"depend de {', '.join(manquantes)}, qui n'a rien produit"
                self._signaler(trace)
                if etape.facultative:
                    continue
                return self._arreter(etape.nom)

            trace.etat = EtatEtape.EN_COURS
            self._signaler(trace)

            await self._executer_avec_etat(etape, trace, acquis)
            if trace.etat is EtatEtape.REUSSIE:
                continue
            if not etape.facultative:
                return self._arreter(etape.nom)

        self.resultat.aboutie = True
        return self.resultat

    async def _executer_avec_etat(self, etape: Etape, trace: Trace,
                                  acquis: Dict[str, Any]) -> None:
        """Fait tourner une etape et pose son etat final — partage entre
        `executer()` (sequentiel) et `executer_parallele()` (par vagues),
        pour qu'aucune des deux voies n'ait sa propre logique d'etat."""
        if await self._tenter(etape, trace, acquis):
            trace.etat = EtatEtape.REUSSIE
            acquis[etape.nom] = trace.resultat
        else:
            trace.etat = (EtatEtape.ABANDONNEE if etape.facultative
                          else EtatEtape.ECHOUEE)
        self._signaler(trace)

    async def executer_parallele(self, parallelisme: int = 4,
                                 limites_ressources: Optional[Dict[str, int]] = None
                                 ) -> Resultat:
        """Comme `executer()`, mais lance en parallele (borne) les etapes
        dont les dependances sont deja satisfaites, au lieu de les attendre
        une par une dans l'ordre de la liste.

        Memes six regles que `executer()` — seul l'ORDRE D'EXECUTION change,
        jamais la signification d'un etat. Une etape dont une dependance
        echoue est ABANDONNEE/ECHOUEE exactement comme dans `executer()`,
        au moment ou cette dependance se resout plutot qu'a une position fixe
        dans une liste.

        `limites_ressources` borne en plus, PAR NOM (`Etape.ressource`), le
        nombre d'etapes d'un meme groupe qui tournent en meme temps — une
        generation WanGP et une analyse Vision locale partagent le meme GPU
        physique (RTX A2000, une seule carte) et ne doivent jamais tourner
        ensemble, meme si rien d'autre ne les en empeche. Une etape deja
        lancee n'est jamais annulee si une autre echoue : arreter un rendu
        WanGP a mi-chemin gaspillerait le temps GPU deja engage pour rien.

        Une dependance circulaire (ou vers un nom qui ne correspond a
        aucune etape) ne fait jamais boucler l'executeur : les etapes
        concernees sont marquees ECHOUEE avec la raison, explicitement.
        """
        limites_ressources = dict(limites_ressources or {})
        acquis: Dict[str, Any] = {}
        global_sem = asyncio.Semaphore(max(1, parallelisme))
        semaphores_ressource = {nom: asyncio.Semaphore(max(1, limite))
                                for nom, limite in limites_ressources.items()}
        par_nom = {etape.nom: (etape, trace) for etape, trace in
                   zip(self.etapes, self.resultat.traces, strict=True)}
        lancees: set = set()
        arretee = False

        async def executer_une(etape: Etape, trace: Trace) -> None:
            sem_ressource = (semaphores_ressource.get(etape.ressource)
                             if etape.ressource else None)
            async with global_sem:
                if sem_ressource is not None:
                    async with sem_ressource:
                        await self._executer_avec_etat(etape, trace, acquis)
                else:
                    await self._executer_avec_etat(etape, trace, acquis)

        while len(lancees) < len(self.etapes) and not arretee:
            pretes: List[Tuple[Etape, Trace]] = []
            for etape, trace in par_nom.values():
                if etape.nom in lancees:
                    continue
                en_attente = False
                manquantes: List[str] = []
                for nom_dep in etape.depend_de:
                    paire = par_nom.get(nom_dep)
                    if paire is None:
                        manquantes.append(nom_dep)
                        continue
                    etat_dep = paire[1].etat
                    if etat_dep in (EtatEtape.EN_ATTENTE, EtatEtape.EN_COURS):
                        en_attente = True
                        break
                    if etat_dep is not EtatEtape.REUSSIE:
                        manquantes.append(nom_dep)
                if en_attente:
                    continue
                if manquantes:
                    trace.etat = (EtatEtape.ABANDONNEE if etape.facultative
                                  else EtatEtape.ECHOUEE)
                    trace.raison = (f"depend de {', '.join(manquantes)}, "
                                    "qui n'a rien produit")
                    self._signaler(trace)
                    lancees.add(etape.nom)
                    if not etape.facultative:
                        arretee = True
                        self.resultat.arretee_a = etape.nom
                    continue
                pretes.append((etape, trace))

            if not pretes:
                if arretee:
                    break
                # Aucune etape prete, aucune EN_COURS, et pas encore arretee :
                # une dependance ne se resoudra jamais (cycle, ou nom
                # inconnu qui n'a pas ete detecte ci-dessus faute d'etre
                # deja "manquante" pour un etat non-final). On ne boucle
                # jamais en silence.
                for etape, trace in par_nom.values():
                    if etape.nom not in lancees:
                        trace.etat = EtatEtape.ECHOUEE
                        trace.raison = "dependance circulaire ou jamais resolue"
                        self._signaler(trace)
                        lancees.add(etape.nom)
                        if not self.resultat.arretee_a:
                            self.resultat.arretee_a = etape.nom
                arretee = True
                break

            for etape, trace in pretes:
                trace.etat = EtatEtape.EN_COURS
                self._signaler(trace)
                lancees.add(etape.nom)

            await asyncio.gather(*(executer_une(etape, trace) for etape, trace in pretes))

            for etape, trace in pretes:
                if trace.etat is not EtatEtape.REUSSIE and not etape.facultative:
                    arretee = True
                    if not self.resultat.arretee_a:
                        self.resultat.arretee_a = etape.nom

        if arretee:
            for trace in self.resultat.traces:
                if trace.etat is EtatEtape.EN_ATTENTE:
                    trace.etat = EtatEtape.NON_ATTEINTE
        else:
            self.resultat.aboutie = True
        return self.resultat

    def _arreter(self, nom: str) -> Resultat:
        """Arrete la tache et marque ce qui n'a jamais ete atteint."""
        self.resultat.arretee_a = nom
        vu = False
        for trace in self.resultat.traces:
            if trace.nom == nom:
                vu = True
                continue
            if vu and trace.etat is EtatEtape.EN_ATTENTE:
                trace.etat = EtatEtape.NON_ATTEINTE
        return self.resultat


def _prend_acquis(appel: Callable[..., Any]) -> bool:
    """Dit si l'appel veut recevoir ce que les etapes precedentes ont produit."""
    try:
        return bool(inspect.signature(appel).parameters)
    except (TypeError, ValueError):
        return False
