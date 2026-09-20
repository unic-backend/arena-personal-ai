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

6. **Ce qui n'est pas ecrit n'a pas eu lieu.** (19/09/2026) Chaque changement
   d'etat est persiste immediatement. Avant, cette file etait deux
   dictionnaires en memoire : un redemarrage d'ARENA effacait tout, et une
   conversion en lot a moitie faite disparaissait sans laisser de trace.

---

## Ce qu'une reprise peut et ne peut PAS faire ici

**Le corps d'un travail est une closure Python.** Il ne se serialise pas, et
pretendre le contraire serait le genre de mensonge que ce depot refuse partout
ailleurs. Un travail ne « redemarre » donc jamais tout seul a partir de son
journal.

Ce qui EST possible, et c'est ce que ce module fait :

- **Rien ne disparait en silence.** Un travail laisse `EN_ATTENTE` ou
  `EN_COURS` par un arret brutal devient `INTERROMPU` au rechargement. Jamais
  `TERMINE`, jamais efface.
- **Rien ne se refait deux fois.** Une `cle` d'execution donnee a
  `soumettre()` rend le travail deja TERMINE sous cette cle au lieu d'en
  lancer un second. C'est la regle d'idempotence, et c'est elle qui protege
  une conversion en lot d'etre rejouee sur des fichiers deja produits.
- **Ce qu'un travail EST peut etre rejoue.** Un travail peut declarer un
  `descripteur` — un type et des parametres, **des donnees**, jamais du code.
  Au demarrage, `reprendre_les_interrompus()` reconstruit l'appel a partir des
  fabriques qu'on lui donne. Un travail sans descripteur reste `INTERROMPU` et
  se voit : c'est une information, pas un echec silencieux.
"""
import asyncio
import inspect
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.execution.journal_disque import ecrire_json_atomique, lire_json

logger = logging.getLogger("usman.execution.travaux")

#: Longueur maximale d'une raison d'echec conservee. Un message d'exception peut
#: transporter une adresse complete : on garde de quoi diagnostiquer, pas de quoi
#: divulguer.
RAISON_MAX = 200

#: Combien de travaux FINIS (TERMINE/ECHOUE/ANNULE) restent dans l'inventaire.
#: Le parallelisme est borne par le semaphore (regle 3), mais rien ne bornait
#: le nombre de travaux **accumules** : un serveur de longue duree grossirait
#: sans fin. Les travaux en cours ne sont jamais purges, quel que soit leur
#: nombre — seul l'historique des travaux finis est plafonne.
TRAVAUX_TERMINES_GARDES = 200


class EtatTravail(str, Enum):
    """Les six etats possibles. Aucun n'est deduit : chacun est ecrit.

    `INTERROMPU` est le seul qui ne soit pose par aucune execution : il est
    pose au RECHARGEMENT, sur un travail que plus aucun processus ne porte.
    Le confondre avec `ECHOUE` dirait « ce travail a rate » la ou la verite
    est « ce travail n'a jamais eu sa reponse ».
    """

    EN_ATTENTE = "PENDING"
    EN_COURS = "RUNNING"
    TERMINE = "DONE"
    ECHOUE = "FAILED"
    ANNULE = "CANCELLED"
    INTERROMPU = "PAUSED"


#: Etats dont on ne revient pas. **`INTERROMPU` n'en fait pas partie** : c'est
#: exactement l'etat depuis lequel on repart.
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
    #: La cle d'execution. Deux soumissions portant la MEME cle ne doivent pas
    #: produire deux fois le meme effet irreversible. Vide = pas de garde.
    cle: str = ""
    #: Ce que ce travail EST, en donnees : `{"type": "...", "parametres": {...}}`.
    #: Jamais du code. C'est ce qui permet de le reconstruire au demarrage.
    #: Vide = ce travail ne sait pas se decrire, donc il ne se reprend pas —
    #: et il le dit au lieu de disparaitre.
    descripteur: Dict[str, Any] = field(default_factory=dict)

    @property
    def fini(self) -> bool:
        return self.etat in ETATS_FINAUX

    @property
    def reprenable(self) -> bool:
        """Interrompu ET capable de dire ce qu'il etait.

        Un travail interrompu sans descripteur n'est pas reprenable : il reste
        visible, avec sa raison. Le compter reprenable promettrait une reprise
        que rien ne peut tenir.
        """
        return self.etat is EtatTravail.INTERROMPU and bool(self.descripteur)

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
            "cle": self.cle,
            "descripteur": self.descripteur,
            "reprenable": self.reprenable,
        }


class FileDeTravaux:
    """Une file de travaux de fond, bornee, qui ne bloque jamais l'appelant.

    Le travail soumis recoit un `Travail` mutable : il peut y avancer `faits`
    au fur et a mesure, ce qui rend la progression observable sans interroger le
    travail lui-meme.
    """

    def __init__(self, parallelisme: int = 1,
                 fichier: Optional[Path] = None) -> None:
        if parallelisme < 1:
            raise ValueError("Une file qui n'execute rien n'est pas une file.")
        self.parallelisme = parallelisme
        self._verrou = asyncio.Semaphore(parallelisme)
        self._travaux: Dict[str, Travail] = {}
        self._taches: Dict[str, asyncio.Task] = {}
        #: `None` : la file ne persiste rien. C'est le defaut, et c'est
        #: delibere — brancher un disque partout ferait ecrire des fichiers a
        #: des tests d'autres modules qui n'en demandent pas.
        self.fichier = Path(fichier) if fichier else None
        if self.fichier is not None:
            self._charger()

    # --- Le disque ---------------------------------------------------------------

    def _charger(self) -> None:
        """Relit la file, et marque ce que plus aucun processus ne porte.

        Au demarrage rien ne tourne : un travail `EN_ATTENTE` ou `EN_COURS`
        retrouve ici a ete tue en route. Il devient `INTERROMPU` — jamais
        `TERMINE` (ce serait un mensonge), jamais efface (ce serait une perte).
        """
        if self.fichier is None:
            return
        brut = lire_json(self.fichier, quoi="File de travaux")
        for donnees in brut.get("travaux", []):
            travail = self._relire(donnees)
            if travail is not None:
                self._travaux[travail.identifiant] = travail

    @staticmethod
    def _relire(donnees):
        """Un travail du disque. Une ligne illisible est ignoree, pas fatale."""
        if not isinstance(donnees, dict):
            return None
        try:
            travail = Travail(
                nom=str(donnees.get("nom", "")),
                etat=EtatTravail(donnees.get("etat", "PENDING")),
                identifiant=str(donnees["id"]),
                cree_le=str(donnees.get("cree_le", _maintenant())),
                demarre_le=donnees.get("demarre_le"),
                fini_le=donnees.get("fini_le"),
                raison=str(donnees.get("raison", "")),
                faits=int(donnees.get("faits", 0)),
                total=donnees.get("total"),
                cle=str(donnees.get("cle", "")),
                descripteur=dict(donnees.get("descripteur") or {}),
            )
        except (KeyError, TypeError, ValueError) as erreur:
            logger.warning("Travail illisible dans le journal (%s) : ignore.", erreur)
            return None

        # **Le resultat n'est jamais ecrit sur le disque**, donc jamais relu
        # (`Travail.to_dict` ne le porte pas). Deux raisons, et la seconde
        # pese plus que la premiere :
        #
        # - un resultat non serialisable deviendrait une chaine `repr`, qu'un
        #   appelant traiterait comme le vrai objet ;
        # - un resultat porte souvent le contenu du proprietaire — chemins de
        #   ses fichiers, extraits de ses documents. Ce journal sert a savoir
        #   CE QUI a tourne, pas a archiver ce que ca a produit.
        #
        # Apres un redemarrage, `resultat` vaut donc `None` : l'etat est exact,
        # le contenu est a redemander a qui le detient.
        if travail.etat in (EtatTravail.EN_ATTENTE, EtatTravail.EN_COURS):
            travail.etat = EtatTravail.INTERROMPU
            travail.raison = (travail.raison
                              or "arrete par un redemarrage, resultat inconnu")
        return travail

    def _ecrire(self) -> None:
        if self.fichier is None:
            return
        ecrire_json_atomique(
            self.fichier,
            {"travaux": [t.to_dict() for t in self._travaux.values()]},
            prefixe=".travaux-", quoi="File de travaux")

    # --- Soumission ------------------------------------------------------------

    def soumettre(
        self,
        nom: str,
        appel: Callable[..., Any],
        total: Optional[int] = None,
        passer_le_travail: bool = False,
        cle: str = "",
        descripteur: Optional[Dict[str, Any]] = None,
    ) -> Travail:
        """Inscrit un travail et rend la main **immediatement**.

        Args:
            nom: le nom du travail, tel qu'il apparaitra dans l'inventaire.
            appel: ce qu'il faut faire. Synchrone ou asynchrone.
            total: le nombre d'unites a traiter, quand il est connu d'avance.
            passer_le_travail: si vrai, `appel` recoit le `Travail` en argument
                et peut y avancer `faits`.
            cle: la cle d'execution. Si un travail DEJA TERMINE la porte, ce
                travail-ci n'est pas lance et l'ancien est rendu tel quel.
                C'est la regle d'idempotence : meme demande, meme cle, un seul
                effet. Un travail echoue, annule ou interrompu ne bloque rien
                — le rejouer est precisement ce qu'on veut.
            descripteur: ce que ce travail EST, en donnees pures
                (`{"type": ..., "parametres": {...}}`). Persiste, et relu au
                demarrage pour reconstruire l'appel. Jamais du code.

        Returns:
            Le `Travail`, deja inscrit, encore `EN_ATTENTE`. Son corps n'a pas
            commence : il demarrera quand la boucle rendra la main.
        """
        if cle:
            deja = self.travail_par_cle(cle)
            if deja is not None:
                logger.info("Travail deja termine sous la cle %s : %s non relance.",
                            cle, nom)
                return deja

        travail = Travail(nom=nom, total=total, cle=cle,
                          descripteur=dict(descripteur or {}))
        self._travaux[travail.identifiant] = travail
        self._ecrire()
        tache = asyncio.get_running_loop().create_task(
            self._executer(travail, appel, passer_le_travail))
        self._taches[travail.identifiant] = tache
        logger.debug("Travail soumis : %s (%s).", nom, travail.identifiant)
        return travail

    def travail_par_cle(self, cle: str) -> Optional[Travail]:
        """Le travail DEJA TERMINE portant cette cle, ou `None`.

        Seul `TERMINE` compte. Un travail echoue sous la meme cle ne doit pas
        interdire un nouvel essai — ce serait figer une panne passagere en
        refus permanent.
        """
        if not cle:
            return None
        return next((t for t in self._travaux.values()
                     if t.cle == cle and t.etat is EtatTravail.TERMINE), None)

    async def _executer(self, travail: Travail, appel: Callable[..., Any],
                        passer_le_travail: bool) -> None:
        """Le corps du travail. Aucune exception n'en sort."""
        async with self._verrou:
            if travail.etat is EtatTravail.ANNULE:
                self._purger_les_anciens()
                self._ecrire()
                return  # annule avant d'avoir commence : on ne le lance pas
            travail.etat = EtatTravail.EN_COURS
            travail.demarre_le = _maintenant()
            # Ecrit AVANT de commencer : c'est cette fenetre-la qu'un arret
            # brutal doit laisser visible. Sans elle, un travail tue en plein
            # milieu se relirait comme s'il n'avait jamais ete soumis.
            self._ecrire()
            try:
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
            finally:
                self._purger_les_anciens()
                self._ecrire()

    def _purger_les_anciens(self) -> None:
        """Retire les travaux FINIS les plus anciens au-dela de la limite.

        Jamais un travail EN_ATTENTE ou EN_COURS : seul l'historique deja
        fini (TERMINE/ECHOUE/ANNULE) est plafonne, et la tache associee est
        deja terminee a ce stade (`_taches` peut donc etre purge avec).
        """
        # Un travail INTERROMPU n'est pas fini : il n'entre pas dans la purge,
        # donc un redemarrage ne peut pas faire disparaitre ce qu'il a laisse.
        finis = sorted(
            (t for t in self._travaux.values() if t.fini),
            key=lambda t: t.fini_le or "",
        )
        exces = len(finis) - TRAVAUX_TERMINES_GARDES
        if exces <= 0:
            return
        for travail in finis[:exces]:
            self._travaux.pop(travail.identifiant, None)
            self._taches.pop(travail.identifiant, None)

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

    def interrompus(self) -> List[Travail]:
        """Les travaux que l'arret precedent a laisses en plan.

        Tous, pas seulement ceux qui savent se reprendre : un travail
        interrompu sans descripteur est une information — il a existe, il n'a
        pas abouti, et personne ne peut le relancer automatiquement.
        """
        return self.inventaire(EtatTravail.INTERROMPU)

    def reprendre_les_interrompus(
        self, fabriques: Dict[str, Callable[[Dict[str, Any]], Any]],
    ) -> List[Travail]:
        """Re-soumet les travaux interrompus dont le type est connu.

        **Une closure ne se serialise pas.** C'est pour ca qu'on ne relance pas
        « le travail » : on le RECONSTRUIT a partir de son descripteur, avec
        une fabrique que l'appelant fournit. Le journal ne porte que des
        donnees ; le code reste dans le code.

        Args:
            fabriques: `type -> (parametres) -> appel`. Un type absent de cette
                table laisse son travail `INTERROMPU`, visible, avec sa raison.
                C'est voulu : inventer une reprise pour un type inconnu serait
                pire que de ne pas reprendre.

        Returns:
            Les nouveaux travaux soumis. Les anciens restent au journal, a
            l'etat `INTERROMPU` : l'histoire ne se reecrit pas.
        """
        repris: List[Travail] = []
        for ancien in self.interrompus():
            # Un travail sans descripteur porte un type vide : la table n'a
            # pas d'entree pour lui, et il reste interrompu par le MEME chemin
            # qu'un type inconnu. Un `if not reprenable` ici serait une
            # deuxieme garde sur la meme porte — donc une branche morte,
            # qu'aucun sabotage ne peut faire mordre.
            type_ = str(ancien.descripteur.get("type", ""))
            fabrique = fabriques.get(type_)
            if fabrique is None:
                logger.info("Travail interrompu %s : type %r sans fabrique, "
                            "il reste a reprendre a la main.", ancien.nom, type_)
                continue
            parametres = dict(ancien.descripteur.get("parametres") or {})
            try:
                appel = fabrique(parametres)
            except Exception as erreur:  # noqa: BLE001 — une fabrique cassee n'arrete rien
                logger.warning("Fabrique %r en echec (%s) : %s reste interrompu.",
                               type_, erreur, ancien.nom)
                continue
            repris.append(self.soumettre(
                ancien.nom, appel, total=ancien.total,
                passer_le_travail=bool(ancien.descripteur.get("passer_le_travail")),
                cle=ancien.cle, descripteur=ancien.descripteur,
            ))
        return repris

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
        self._ecrire()
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
