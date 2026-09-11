"""Un verrou par chemin de fichier — deux tâches ne corrompent jamais le même.

**Le risque, mesuré avant d'écrire une ligne.** `apps/backend/runtime.py`
instancie UN SEUL `DioumtoukayAgent`, avec UN SEUL `Atelier` partagé. Sa
boucle (`run()`) est `async` et attend le modèle (`await self.provider.
generate(...)`) à chaque tour — un appel réseau/Ollama, donc un vrai point où
FastAPI peut faire avancer une AUTRE requête concurrente. Deux conversations
qui demandent toutes les deux à Dioumtoukay de travailler EN MÊME TEMPS sur
le même dépôt peuvent donc réellement entrelacer leurs actions sur le MÊME
fichier — mission ARENA x TRANS4MERS §20/§51.

**Ce que ce module n'est PAS.** DEC-0038 est claire : « pas de garde-fou
ici. Aucune confirmation, aucun chemin interdit, aucune commande refusée. »
Ce module ne refuse JAMAIS une action et n'ajoute AUCUNE confirmation — il
sérialise. Deux écritures concurrentes sur le même fichier s'exécutent l'une
après l'autre au lieu de s'entrelacer ; rien n'est bloqué plus de quelques
millisecondes (le temps d'une écriture disque), rien n'est jamais rejeté.
C'est un mutex de correction, pas une porte d'autorisation — la même
distinction que `threading.Lock` face à un contrôle d'accès.

**Granularité : le fichier, rien de plus.** Mission §21 : « use only the
granularity actually needed ». `Atelier` n'acquiert ni GPU, ni port, ni
modèle — verrouiller à ces niveaux protégerait des ressources qu'il ne
possède jamais. `executer()` n'est délibérément PAS verrouillé : une commande
shell peut tourner jusqu'à 120s (`DELAI_PAR_DEFAUT`) et toucher n'importe quel
nombre de fichiers, ou aucun — l'y soumettre bloquerait un chemin sans
rapport pendant deux minutes pour une protection qu'on ne peut pas nommer.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Sequence

#: Un verrou par chemin **canonique** (résolu : `..`, liens symboliques et
#: chemins relatifs différents vers le même fichier convergent vers la même
#: clé). Deux chemins qui *paraissent* différents mais désignent le même
#: fichier doivent partager le même verrou, sinon la protection ne protège
#: rien.
_verrous: Dict[str, threading.Lock] = {}
#: Protège la création d'un verrou lui-même — sans ça, deux tâches pourraient
#: chacune créer SON propre `Lock()` pour le même chemin au même instant, et
#: se retrouver avec deux verrous distincts qui ne s'excluent pas.
_meta = threading.Lock()


def _cle(chemin: Path) -> str:
    """Le chemin, résolu — jamais tel quel, pour que `a/../b` et `b` partagent
    le même verrou. `strict=False` : le fichier peut ne pas encore exister
    (c'est le cas normal d'`ecrire()` qui le crée)."""
    return str(chemin.resolve(strict=False))


def _verrou_pour(chemin: Path) -> threading.Lock:
    cle = _cle(chemin)
    with _meta:
        verrou = _verrous.get(cle)
        if verrou is None:
            verrou = threading.Lock()
            _verrous[cle] = verrou
        return verrou


@contextmanager
def pour(chemin: Path) -> Iterator[None]:
    """Sérialise l'accès à UN chemin. Attend son tour, ne refuse jamais rien."""
    verrou = _verrou_pour(chemin)
    with verrou:
        yield


@contextmanager
def pour_plusieurs(chemins: Sequence[Path]) -> Iterator[None]:
    """Sérialise l'accès à PLUSIEURS chemins à la fois (`deplacer`/`copier` :
    source ET destination). Acquis dans un **ordre total et stable**
    (le chemin canonique trié) — mission §21, « define lock ordering » :
    sans un ordre fixe, une tâche qui verrouille A puis B et une autre qui
    verrouille B puis A peuvent s'attendre indéfiniment l'une l'autre. Trier
    les chemins avant d'acquérir élimine ce cas par construction : toute
    tâche les acquiert dans le même ordre, quel que soit l'ordre dans lequel
    l'appelant les a nommés.
    """
    distincts = sorted({_cle(c): c for c in chemins}.items())
    verrous = [_verrou_pour(chemin) for _, chemin in distincts]
    acquis = []
    try:
        for verrou in verrous:
            verrou.acquire()
            acquis.append(verrou)
        yield
    finally:
        for verrou in reversed(acquis):
            verrou.release()
