"""Ce que la memoire contient vraiment, mesure sur la machine qui repond.

Ecrit le 19/09/2026. Le proprietaire dit « il oublie ce qu'on s'est dit » ;
trois causes differentes produisent exactement cette phrase, et rien ne
permettait de savoir laquelle agissait :

1. le fil du serveur n'etait pas relu sur le chemin du telephone
   (`core/memory/conversation.py`, corrige le meme jour) ;
2. la recherche de souvenirs tourne en mode lexical des qu'Ollama ne repond
   pas — sur Railway il n'y a pas d'Ollama, donc jamais de recherche par le
   sens (`core/memory/semantique.py`) ;
3. la base est un fichier ; si le disque de l'hebergeur est efface a chaque
   redeploiement, tout repart a zero sans qu'aucun code ne soit en faute.

Ce module ne repare rien. Il **mesure**, pour que la question se tranche au
lieu de se supposer — et il dit `PAS_ENCORE_OBSERVEE` plutot que « non »
quand il n'a pas encore de quoi conclure.

**Trois regles :**

1. **Rien n'est declare.** Chaque chiffre vient d'un `SELECT`, l'etat de la
   recherche d'un vecteur reellement demande. Aucune valeur n'est deduite du
   fait qu'un objet existe.

2. **Une mesure impossible se dit.** Une base illisible rend `None` et sa
   raison, jamais `0` : zero message et base introuvable sont deux faits
   differents, et les confondre enverrait chercher la panne ailleurs.

3. **La persistance s'observe, elle ne se configure pas.** Un souvenir plus
   ancien que le demarrage de ce processus **prouve** que le disque a survecu
   a un redemarrage. Rien d'autre ne le prouve — surtout pas une variable
   d'environnement bien remplie.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("usman.memoire.etat")

#: Quand ce processus a demarre. Sert de temoin de persistance : une ligne
#: ecrite avant cet instant ne peut venir que d'une execution precedente.
DEMARRAGE = datetime.now(timezone.utc)

PERSISTANCE_CONFIRMEE = "CONFIRMEE"
PERSISTANCE_PAS_OBSERVEE = "PAS_ENCORE_OBSERVEE"
PERSISTANCE_INCONNUE = "INCONNUE"

RECHERCHE_PAR_LE_SENS = "SEMANTIQUE"
RECHERCHE_PAR_LES_MOTS = "LEXICAL"
RECHERCHE_INCONNUE = "INCONNUE"


@dataclass(frozen=True)
class EtatBase:
    """Le fichier lui-meme : ou il est, ce qu'il pese, s'il survit."""

    chemin: str
    existe: bool
    octets: Optional[int]
    persistance: str
    detail: str


@dataclass(frozen=True)
class EtatFil:
    """Ce que `short_term_memory` garde des conversations."""

    messages: Optional[int]
    conversations: Optional[int]
    plus_ancien: Optional[str]
    detail: str = ""


@dataclass(frozen=True)
class EtatSouvenirs:
    """Ce que la memoire longue garde."""

    total: Optional[int]
    plus_ancien: Optional[str]
    detail: str = ""


@dataclass(frozen=True)
class EtatRecherche:
    """Comment un souvenir est retrouve **aujourd'hui, ici**."""

    mode: str
    modele: str
    detail: str


def _compter(chemin: Path, requete: str) -> Optional[tuple]:
    """Une ligne de comptage, ou `None` avec la raison dans le journal."""
    if not chemin.exists():
        return None
    try:
        with closing(sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)) as connexion:
            return connexion.execute(requete).fetchone()
    except Exception as erreur:  # noqa: BLE001 — une mesure ratee n'est pas un zero
        logger.warning("Comptage impossible sur %s : %s", chemin, erreur)
        return None


def _plus_ancien_que_le_demarrage(horodatage: Optional[str]) -> bool:
    """Vrai si cette date precede le demarrage de ce processus."""
    if not horodatage:
        return False
    texte = str(horodatage).strip().replace(" ", "T")
    try:
        date = datetime.fromisoformat(texte)
    except ValueError:
        return False
    if date.tzinfo is None:
        # SQLite ecrit `CURRENT_TIMESTAMP` en UTC sans le dire.
        date = date.replace(tzinfo=timezone.utc)
    return date < DEMARRAGE


def etat_base(chemin: Path, plus_ancien: Optional[str]) -> EtatBase:
    """Ou vit la base, et si elle a deja survecu a un redemarrage."""
    chemin = Path(chemin)
    existe = chemin.exists()
    octets = chemin.stat().st_size if existe else None

    if not existe:
        persistance, detail = PERSISTANCE_INCONNUE, "la base n'existe pas encore"
    elif _plus_ancien_que_le_demarrage(plus_ancien):
        persistance = PERSISTANCE_CONFIRMEE
        detail = (f"une ligne du {plus_ancien} precede le demarrage de ce "
                  f"processus ({DEMARRAGE.isoformat(timespec='seconds')}) : "
                  "le disque a survecu a au moins un redemarrage")
    else:
        persistance = PERSISTANCE_PAS_OBSERVEE
        detail = ("tout ce qui est en base a ete ecrit depuis le demarrage de "
                  "ce processus — pas encore de preuve dans un sens ni dans "
                  "l'autre")

    return EtatBase(chemin=str(chemin.resolve() if existe else chemin),
                    existe=existe, octets=octets,
                    persistance=persistance, detail=detail)


def etat_fil(chemin: Path) -> EtatFil:
    """Combien de messages, dans combien de conversations, depuis quand."""
    ligne = _compter(Path(chemin), """
        SELECT COUNT(*), COUNT(DISTINCT session_id), MIN(timestamp)
        FROM short_term_memory
    """)
    if ligne is None:
        return EtatFil(messages=None, conversations=None, plus_ancien=None,
                       detail="table illisible ou absente")
    return EtatFil(messages=ligne[0], conversations=ligne[1], plus_ancien=ligne[2])


def etat_souvenirs(chemin: Path) -> EtatSouvenirs:
    """Combien de souvenirs longs, et depuis quand."""
    ligne = _compter(Path(chemin), """
        SELECT COUNT(*), MIN(cree_le) FROM souvenirs
    """)
    if ligne is None:
        return EtatSouvenirs(total=None, plus_ancien=None,
                             detail="table illisible ou absente")
    return EtatSouvenirs(total=ligne[0], plus_ancien=ligne[1])


async def etat_recherche(mesure=None) -> EtatRecherche:
    """Par le sens ou par les mots — mesure, jamais suppose.

    Le mode n'est pas un reglage : il depend d'un vecteur reellement obtenu
    d'Ollama. Sur l'hebergeur, il n'y a pas d'Ollama, et la recherche compare
    donc des mots. « De quoi on parlait » n'a alors aucun mot commun avec quoi
    que ce soit — ce qui explique une partie des oublis sans qu'aucun code
    soit en faute.
    """
    from core.memory.semantique import MODELE_EMBEDDINGS, mesurer

    try:
        etat = await (mesure or mesurer)()
    except Exception as erreur:  # noqa: BLE001 — l'etat ne doit jamais lever
        return EtatRecherche(mode=RECHERCHE_INCONNUE, modele=MODELE_EMBEDDINGS,
                             detail=f"mesure impossible : {erreur}")
    if etat.disponible:
        return EtatRecherche(mode=RECHERCHE_PAR_LE_SENS, modele=etat.modele,
                             detail=f"vecteur obtenu, dimension {etat.dimension}")
    return EtatRecherche(mode=RECHERCHE_PAR_LES_MOTS, modele=etat.modele,
                         detail=f"{etat.etat} — {etat.detail}")


async def etat_memoire(chemin: Path, mesure=None) -> Dict[str, Any]:
    """Le rapport complet, pret a etre rendu par une route.

    Args:
        chemin: le fichier de base (`DB_PATH`).
        mesure: de quoi remplacer la sonde d'embeddings dans un test.
    """
    fil = etat_fil(chemin)
    souvenirs = etat_souvenirs(chemin)
    # La date de reference pour la persistance est la plus ancienne des deux :
    # une base peut ne contenir que des souvenirs, ou que des messages.
    dates = [d for d in (fil.plus_ancien, souvenirs.plus_ancien) if d]
    return {
        "base": asdict(etat_base(chemin, min(dates) if dates else None)),
        "fil": asdict(fil),
        "souvenirs": asdict(souvenirs),
        "recherche": asdict(await etat_recherche(mesure)),
    }
