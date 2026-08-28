"""Faire tourner un travail long sans que la conversation en paie le prix.

Indexer des documents, analyser une video, preparer un rapport : ces choses
durent des minutes. Si elles tournent sur le chemin de la reponse, le chat
attend. La specification (§15) demande l'inverse : le travail de fond avance,
et la latence du chat ne bouge pas.

**Cinq regles :**

1. **`soumettre()` n'execute rien.** Elle inscrit le travail, rend un
   identifiant, et rend la main. Le corps du travail demarre sur la boucle, pas
   dans l'appelant — c'est toute la difference entre « en tache de fond » et
   « avant de repondre ».

2. **Une panne de fond ne remonte jamais au chat.** Un travail qui leve devient
   `ECHOUE` avec sa raison. Rien ne se propage vers la reponse en cours : une
   indexation ratee ne doit pas casser un « bonjour ».

3. **Le parallelisme est borne.** Une seule carte graphique, une seule file.
   Dix travaux soumis ne font pas dix travaux simultanes.

4. **La progression se compte.** `faits / total` d'une unite reelle. Un total
   inconnu vaut `None` — jamais `0`, qui se lirait comme « rien a faire », ni
   `100 %`, qui se lirait comme « fini ».

5. **Annuler est definitif et idempotent.** Annuler deux fois n'annule qu'une
   fois, et un travail deja fini ne redevient pas annulable.
"""
import asyncio
import inspect
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("usman.execution.travaux")

#: Longueur maximale d'une raison d'echec conservee. Un message d'exception peut
#: transporter une adresse complete : on garde de quoi diagnostiquer, pas de quoi
#: divulguer.
RAISON_MAX = 200


class EtatTravail(str, Enum):
    """Les cinq etats possibles. Aucun n'est deduit : chacun est ecrit."""

    EN_ATTENTE = "PENDING"
    EN_COURS = "RUNNING"
    TERMINE = "DONE"
    ECHOUE = "FAILED"
    ANNULE = "CANCELLED"


#: Etats dont on ne revient pas.
ETATS_FINAUX = frozenset({EtatTravail.TERMINE, EtatTravail.ECHOUE, EtatTravail.ANNULE})


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Travail:
    """Un travail de fond : ce qu'il est, ou il en est, ce qu'il a donne."""

    nom: str
    etat: EtatTravail = EtatTravail.EN_ATTENTE
    identifiant: str = field(default_factory=lambda: uuid.uuid4().hex)
    cree_le: str = field(default_factory=_maintenant)
    demarre_le: Optional[str] = None
    fini_le: Optional[str] = None
    resultat: Any = None
    raison: str = ""
    faits: int = 0
    total: Optional[int] = None

    @property
    def fini(self) -> bool:
        return self.etat in ETATS_FINAUX

    @property
    def progression(self) -> Optional[float]:
        """`faits / total`, ou `None` quand le total n'est pas connu.

        Rendre `0.0` pour un total inconnu ferait lire « rien n'avance » la ou
        la verite est « on ne sait pas combien il y a a faire ».
        """
        if self.total is None or self.total <= 0:
            return None
        return min(1.0, self.faits / self.total)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.identifiant,
            "nom": self.nom,
            "etat": self.etat.value,
            "cree_le": self.cree_le,
            "demarre_le": self.demarre_le,
            "fini_le": self.fini_le,
            "faits": self.faits,
            "total": self.total,
            "progression": self.progression,
            "raison": self.raison,
        }


class FileDeTravaux:
    """Une file de travaux de fond, bornee, qui ne bloque jamais l'appelant.

    Le travail soumis recoit un `Travail` mutable : il peut y avancer `faits`
    au fur et a mesure, ce qui rend la progression observable sans interroger le
    travail lui-meme.
    """

    def __init__(self, parallelisme: int = 1) -> None:
        if parallelisme < 1:
            raise ValueError("Une file qui n'execute rien n'est pas une file.")
        self.parallelisme = parallelisme
        self._verrou = asyncio.Semaphore(parallelisme)
        self._travaux: Dict[str, Travail] = {}
        self._taches: Dict[str, asyncio.Task] = {}

    # --- Soumission ------------------------------------------------------------

    def soumettre(
        self,
        nom: str,
        appel: Callable[..., Any],
        total: Optional[int] = None,
        passer_le_travail: bool = False,
    ) -> Travail:
        """Inscrit un travail et rend la main **immediatement**.

        Args:
            nom: le nom du travail, tel qu'il apparaitra dans l'inventaire.
            appel: ce qu'il faut faire. Synchrone ou asynchrone.
            total: le nombre d'unites a traiter, quand il est connu d'avance.
            passer_le_travail: si vrai, `appel` recoit le `Travail` en argument
                et peut y avancer `faits`.

        Returns:
            Le `Travail`, deja inscrit, encore `EN_ATTENTE`. Son corps n'a pas
            commence : il demarrera quand la boucle rendra la main.
        """
        travail = Travail(nom=nom, total=total)
        self._travaux[travail.identifiant] = travail
        tache = asyncio.get_running_loop().create_task(
            self._executer(travail, appel, passer_le_travail))
        self._taches[travail.identifiant] = tache
        logger.debug("Travail soumis : %s (%s).", nom, travail.identifiant)
        return travail

    async def _executer(self, travail: Travail, appel: Callable[..., Any],
                        passer_le_travail: bool) -> None:
        """Le corps du travail. Aucune exception n'en sort."""
        async with self._verrou:
            if travail.etat is EtatTravail.ANNULE:
                return  # annule avant d'avoir commence : on ne le lance pas
            travail.etat = EtatTravail.EN_COURS
            travail.demarre_le = _maintenant()
            try:
                resultat = appel(travail) if passer_le_travail else appel()
                if inspect.isawaitable(resultat):
                    resultat = await resultat
            except asyncio.CancelledError:
                travail.etat = EtatTravail.ANNULE
                travail.fini_le = _maintenant()
                raise
            except Exception as erreur:  # noqa: BLE001 — une panne de fond reste au fond
                travail.etat = EtatTravail.ECHOUE
                travail.raison = f"{type(erreur).__name__}: {erreur}"[:RAISON_MAX]
                travail.fini_le = _maintenant()
                logger.info("Travail %s echoue : %s", travail.nom, travail.raison)
                return
            travail.resultat = resultat
            travail.etat = EtatTravail.TERMINE
            travail.fini_le = _maintenant()

    # --- Lecture ---------------------------------------------------------------

    def lire(self, identifiant: str) -> Optional[Travail]:
        return self._travaux.get(identifiant)

    def inventaire(self, etat: Optional[EtatTravail] = None) -> List[Travail]:
        """Tous les travaux, du plus recent au plus ancien. Rien n'est cache."""
        travaux = sorted(self._travaux.values(), key=lambda t: t.cree_le, reverse=True)
        if etat is None:
            return travaux
        return [travail for travail in travaux if travail.etat is etat]

    @property
    def en_cours(self) -> int:
        return len(self.inventaire(EtatTravail.EN_COURS))

    # --- Annulation et attente --------------------------------------------------

    def annuler(self, identifiant: str) -> bool:
        """Annule un travail. Rend `False` s'il est deja fini ou inconnu.

        Idempotent : annuler deux fois rend `True` puis `False`, et n'annule
        qu'une fois.
        """
        travail = self._travaux.get(identifiant)
        if travail is None or travail.fini:
            return False
        tache = self._taches.get(identifiant)
        travail.etat = EtatTravail.ANNULE
        travail.fini_le = _maintenant()
        travail.raison = "annule"
        if tache is not None and not tache.done():
            tache.cancel()
        return True

    async def attendre(self, identifiant: str, delai: float = 5.0) -> Optional[Travail]:
        """Attend la fin d'un travail. **Pour les tests et l'outillage** — le
        chemin de reponse, lui, ne doit jamais attendre un travail de fond.
        """
        tache = self._taches.get(identifiant)
        if tache is None:
            return None
        try:
            await asyncio.wait_for(asyncio.shield(tache), timeout=delai)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        return self._travaux.get(identifiant)

    async def fermer(self, delai: float = 5.0) -> None:
        """Attend tous les travaux en vol, puis rend la main."""
        taches = [t for t in self._taches.values() if not t.done()]
        if not taches:
            return
        await asyncio.wait(taches, timeout=delai)
