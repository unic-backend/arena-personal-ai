"""Une tâche interrompue reprend là où elle s'est arrêtée. Rien ne se refait.

**Le manque mesuré le 07/09/2026.** `DioumtoukayAgent` travaille par tours
bornés — douze actions, vingt minutes. Quand il touche une borne, il rend
honnêtement *« Arrêté après N minutes sans avoir conclu. Ce qui a été fait est
ci-dessous ; la suite reste à faire. »* et garde un **résumé en prose** dans la
mémoire longue.

Un résumé n'est pas un état. « Reprends ce que tu faisais » relançait donc le
travail **depuis zéro** : mêmes lectures, mêmes recherches, mêmes commandes,
avant de retrouver le point d'arrêt — quand il le retrouvait. Et
`core/execution/travaux.py` ne pouvait pas aider : sa file est purement en
mémoire (deux dictionnaires dans `__init__`), donc un redémarrage d'ARENA
efface tout.

C'est le seul manque réel qu'a révélé la comparaison avec `langchain-ai/open-swe`
(DEC-0072). Leur mécanique — dispatch durable, `reconcile.py` qui balaie les
exécutions bloquées — est indissociable de LangGraph et de sa plateforme. Ce
module en reprend **les deux idées**, écrites pour ARENA :

1. **Un journal d'étapes durable**, sur disque, écrit après chaque action.
2. **Un balayage** qui marque interrompue une tâche qui n'avance plus, pour
   qu'elle ne reste pas « en cours » éternellement.

---

## Trois règles

1. **Ce qui n'est pas écrit n'a pas eu lieu.** Chaque étape est persistée
   immédiatement, pas à la fin : une tâche tuée au milieu doit laisser
   exactement ce qu'elle avait fait, pas moins.

2. **Reprendre n'est pas deviner.** Une tâche ne se reprend que si son état le
   dit (`INTERROMPUE`) et si sa demande est la même. Rapprocher deux demandes
   voisines ferait continuer un travail sur un autre sujet — pire que
   recommencer.

3. **Un journal qui casse ne casse pas le travail.** Un fichier illisible, un
   disque plein, un JSON corrompu : la tâche continue sans reprise et le dit.
   Perdre la mémoire d'un travail est ennuyeux ; perdre le travail parce que
   sa mémoire est en panne serait absurde.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.execution.reprise")

#: Où le journal vit. Hors du dépôt (`data/` est ignoré par git) : il porte les
#: demandes du propriétaire et les chemins de ses fichiers.
FICHIER_PAR_DEFAUT = Path("data") / "travaux" / "reprises.json"

#: Au-delà, une tâche « en cours » qui n'a plus avancé n'est plus en cours :
#: le processus qui la portait est mort. Elle devient INTERROMPUE, donc
#: reprenable. C'est l'idée de `reconcile.py` d'Open SWE, sans sa plateforme.
#: Une heure : largement au-dessus du plafond de 20 minutes de Dioumtoukay,
#: assez bas pour qu'une tâche morte ne bloque pas la journée.
AGE_MAX_SECONDES = 3600.0

#: Combien de tâches terminées on garde. Le journal sert à REPRENDRE, pas à
#: archiver : au-delà, les plus anciennes terminées sont oubliées. Les tâches
#: reprenables ne sont jamais purgées — ce serait perdre du travail.
TERMINEES_GARDEES = 50


class EtatTache(str, Enum):
    """Où en est un travail. Seul `INTERROMPUE` se reprend."""

    EN_COURS = "EN_COURS"
    INTERROMPUE = "INTERROMPUE"
    TERMINEE = "TERMINEE"
    ECHOUEE = "ECHOUEE"


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Etape:
    """Une action et ce qu'elle a donné. L'unité de ce qui ne se refait pas.

    Les champs sont ceux que l'observabilité demande : quel outil, combien de
    temps, réussi ou non. Ils sont écrits par celui qui agit, jamais déduits.
    """

    numero: int
    outil: str
    cible: str = ""
    ok: bool = True
    resume: str = ""
    duree_ms: int = 0
    quand: str = field(default_factory=_maintenant)


@dataclass
class Tache:
    """Un travail, sa demande, et tout ce qui a déjà été fait pour elle."""

    identifiant: str
    demande: str
    etat: EtatTache = EtatTache.EN_COURS
    etapes: List[Etape] = field(default_factory=list)
    conclusion: str = ""
    cree_le: str = field(default_factory=_maintenant)
    maj_le: str = field(default_factory=_maintenant)

    @property
    def reprenable(self) -> bool:
        return self.etat is EtatTache.INTERROMPUE and bool(self.etapes)

    def deja_fait(self) -> List[str]:
        """Ce qui a été fait, en clair, pour le réinjecter dans le travail.

        Rendu sous la forme du journal que l'agent tient déjà pendant sa
        boucle : reprendre, c'est repartir avec ce journal-là, pas avec un
        format nouveau que rien d'autre ne sait lire.
        """
        return [f"{e.outil} {e.cible} -> {'ok' if e.ok else 'echec'} : {e.resume}".strip()
                for e in self.etapes]

    def journal(self) -> Dict[str, Any]:
        """La ligne d'observabilité de la tâche entière."""
        return {"task_id": self.identifiant, "status": self.etat.value,
                "steps": len(self.etapes), "updated": self.maj_le}


class JournalDeReprise:
    """Le journal durable des travaux. Un fichier, écrit après chaque étape."""

    def __init__(self, fichier: Optional[Path] = None,
                 age_max: float = AGE_MAX_SECONDES) -> None:
        self.fichier = Path(fichier) if fichier else FICHIER_PAR_DEFAUT
        self.age_max = age_max
        self._taches: Dict[str, Tache] = {}
        self._charger()

    # --- Disque ---------------------------------------------------------------

    def _charger(self) -> None:
        """Relit le journal. Un fichier illisible n'empêche pas de travailler."""
        if not self.fichier.is_file():
            return
        try:
            brut = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError) as erreur:
            logger.warning("Journal de reprise illisible (%s) : on repart a vide.",
                           erreur)
            return
        for donnees in brut.get("taches", []):
            try:
                tache = Tache(
                    identifiant=str(donnees["identifiant"]),
                    demande=str(donnees.get("demande", "")),
                    etat=EtatTache(donnees.get("etat", "EN_COURS")),
                    etapes=[Etape(**e) for e in donnees.get("etapes", [])],
                    conclusion=str(donnees.get("conclusion", "")),
                    cree_le=str(donnees.get("cree_le", _maintenant())),
                    maj_le=str(donnees.get("maj_le", _maintenant())))
            except (KeyError, TypeError, ValueError) as erreur:
                # Une entree abimee ne doit pas emporter les autres : c'est
                # exactement le travail qu'on cherche a ne pas perdre.
                logger.warning("Tache de reprise ignoree (%s).", erreur)
                continue
            self._taches[tache.identifiant] = tache

    def _ecrire(self) -> None:
        """Écrit le journal. **Atomique** : un remplacement, jamais une troncature.

        Une écriture directe interrompue laisserait un fichier à moitié écrit —
        c'est-à-dire un journal de reprise qu'on ne peut pas relire, dans le
        seul moment où il sert.
        """
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            charge = {"taches": [self._serialiser(t) for t in self._taches.values()]}
            with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=str(self.fichier.parent),
                    prefix=".reprises-", suffix=".tmp", delete=False) as flux:
                json.dump(charge, flux, ensure_ascii=False, indent=1)
                provisoire = Path(flux.name)
            os.replace(provisoire, self.fichier)
        except OSError as erreur:
            logger.warning("Journal de reprise non ecrit (%s) : le travail continue.",
                           erreur)

    @staticmethod
    def _serialiser(tache: Tache) -> Dict[str, Any]:
        donnees = asdict(tache)
        donnees["etat"] = tache.etat.value
        return donnees

    # --- Le cycle d'une tâche --------------------------------------------------

    def ouvrir(self, demande: str) -> Tache:
        """La tâche à faire : une reprise si elle existe, sinon une neuve.

        La reprise exige la **demande identique**. Rapprocher deux demandes
        voisines ferait continuer un travail sur un autre sujet — pire que
        recommencer, parce que personne ne le verrait.
        """
        self.balayer()
        propre = (demande or "").strip()
        for tache in sorted(self._taches.values(), key=lambda t: t.maj_le, reverse=True):
            if tache.reprenable and tache.demande.strip() == propre:
                tache.etat = EtatTache.EN_COURS
                tache.maj_le = _maintenant()
                self._ecrire()
                logger.info("Reprise de la tache %s (%d etapes deja faites).",
                            tache.identifiant, len(tache.etapes))
                return tache

        tache = Tache(identifiant=uuid.uuid4().hex[:12], demande=propre)
        self._taches[tache.identifiant] = tache
        self._purger()
        self._ecrire()
        return tache

    def noter(self, tache: Tache, outil: str, cible: str = "", ok: bool = True,
              resume: str = "", duree_ms: int = 0) -> Etape:
        """Ajoute une étape et l'écrit **tout de suite**.

        Écrire à la fin perdrait exactement ce qu'on cherche à garder : ce
        qu'une tâche tuée au milieu avait déjà accompli.
        """
        etape = Etape(numero=len(tache.etapes) + 1, outil=outil, cible=cible,
                      ok=ok, resume=(resume or "")[:400], duree_ms=duree_ms)
        tache.etapes.append(etape)
        tache.maj_le = _maintenant()
        self._ecrire()
        return etape

    def terminer(self, tache: Tache, conclusion: str = "") -> None:
        self._clore(tache, EtatTache.TERMINEE, conclusion)

    def interrompre(self, tache: Tache, conclusion: str = "") -> None:
        """La tâche s'arrête sans avoir conclu — et pourra donc reprendre."""
        self._clore(tache, EtatTache.INTERROMPUE, conclusion)

    def echouer(self, tache: Tache, conclusion: str = "") -> None:
        """La tâche ne peut pas aboutir. **Elle ne se reprend pas.**

        Rejouer un travail qui a echoue pour une raison qui n'a pas change
        (aucun moteur, un depot absent) le referait echouer a l'identique.
        """
        self._clore(tache, EtatTache.ECHOUEE, conclusion)

    def _clore(self, tache: Tache, etat: EtatTache, conclusion: str) -> None:
        tache.etat = etat
        tache.conclusion = (conclusion or "")[:1000]
        tache.maj_le = _maintenant()
        self._purger()
        self._ecrire()

    # --- Le balayage -----------------------------------------------------------

    def balayer(self) -> List[str]:
        """Marque interrompue toute tâche « en cours » qui n'avance plus.

        L'idée vient de `reconcile.py` d'Open SWE : sans ce filet, une tâche
        dont le processus est mort reste « en cours » pour toujours, et rien ne
        la reprendra jamais — elle est perdue en se déclarant vivante.

        Returns:
            Les identifiants des tâches libérées.
        """
        libérées = []
        limite = time.time() - self.age_max
        for tache in self._taches.values():
            if tache.etat is not EtatTache.EN_COURS:
                continue
            if self._horodatage(tache.maj_le) < limite:
                tache.etat = EtatTache.INTERROMPUE
                tache.conclusion = (
                    "Plus aucune avancee depuis plus d'une heure : le travail "
                    "qui la portait s'est arrete. Elle peut reprendre.")
                libérées.append(tache.identifiant)
        if libérées:
            self._ecrire()
            logger.info("Taches liberees par le balayage : %s", libérées)
        return libérées

    @staticmethod
    def _horodatage(quand: str) -> float:
        """Un horodatage illisible est traité comme ANCIEN, pas comme récent.

        Se tromper dans ce sens libère une tâche vivante — elle reprendra, au
        pire en double. Se tromper dans l'autre garderait pour toujours une
        tâche morte, et c'est précisément ce que ce balayage existe pour
        empêcher.
        """
        try:
            return datetime.fromisoformat(quand).timestamp()
        except (TypeError, ValueError):
            return 0.0

    # --- Lecture ---------------------------------------------------------------

    def lire(self, identifiant: str) -> Optional[Tache]:
        return self._taches.get(identifiant)

    def inventaire(self, etat: Optional[EtatTache] = None) -> List[Tache]:
        taches = list(self._taches.values())
        if etat is not None:
            taches = [t for t in taches if t.etat is etat]
        return sorted(taches, key=lambda t: t.maj_le, reverse=True)

    def _purger(self) -> None:
        """Oublie les plus anciennes TERMINÉES. Jamais une tâche reprenable."""
        terminees = sorted(
            (t for t in self._taches.values() if t.etat is EtatTache.TERMINEE),
            key=lambda t: t.maj_le, reverse=True)
        for tache in terminees[TERMINEES_GARDEES:]:
            self._taches.pop(tache.identifiant, None)
