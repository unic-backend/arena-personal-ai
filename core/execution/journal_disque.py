"""Ecrire un journal sur le disque sans jamais le laisser a moitie ecrit.

Trois modules de ce depot tiennent un journal JSON durable — la reprise des
taches (`core/execution/reprise.py`), l'etat des projets de production
(`core/production/journal_projet.py`) et la file de travaux de fond
(`core/execution/travaux.py`). Les trois avaient la MEME dizaine de lignes
recopiees : fichier temporaire, `json.dump`, `os.replace`, `OSError` avale avec
un avertissement.

Trois copies d'une regle, c'est trois endroits ou la corriger. Elle vit ici.

**Deux regles, et elles ont la meme raison d'etre :**

1. **L'ecriture est atomique.** Un fichier temporaire dans le MEME dossier,
   puis un `os.replace`. Une ecriture directe interrompue laisserait un journal
   a moitie ecrit — c'est-a-dire illisible, dans le seul moment ou il sert.

2. **Un journal casse ne casse pas le travail.** Disque plein, dossier en
   lecture seule, JSON corrompu : la lecture rend le defaut, l'ecriture le
   journalise, et l'appelant continue. Perdre la memoire d'un travail est
   ennuyeux ; perdre le travail parce que sa memoire est en panne serait
   absurde.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("usman.execution.journal_disque")


def lire_json(fichier: Path, defaut: Optional[Dict[str, Any]] = None,
              quoi: str = "journal") -> Dict[str, Any]:
    """Relit un journal. Un fichier absent ou illisible rend `defaut`.

    Args:
        fichier: le chemin du journal.
        defaut: ce qui est rendu quand rien n'est lisible. `None` vaut `{}`.
        quoi: le nom du journal dans l'avertissement, pour qu'un message de
            log dise lequel des trois a un probleme.
    """
    vide = {} if defaut is None else defaut
    if not fichier.is_file():
        return vide
    try:
        charge = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        logger.warning("%s illisible (%s) : on repart a vide.", quoi, erreur)
        return vide
    return charge if isinstance(charge, dict) else vide


def ecrire_json_atomique(fichier: Path, charge: Dict[str, Any],
                         prefixe: str = ".journal-", quoi: str = "journal") -> bool:
    """Ecrit le journal d'un seul remplacement. Rend vrai si l'ecriture a eu lieu.

    Le fichier temporaire vit dans le MEME dossier que la cible : `os.replace`
    n'est atomique qu'a l'interieur d'un meme systeme de fichiers.

    `default=repr` : un resultat de travail peut porter un objet que `json` ne
    sait pas serialiser. Le refuser ferait perdre TOUT le journal pour une
    seule valeur exotique — sa representation est encore une information.
    """
    try:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=str(fichier.parent),
                prefix=prefixe, suffix=".tmp", delete=False) as flux:
            json.dump(charge, flux, ensure_ascii=False, indent=1, default=repr)
            provisoire = Path(flux.name)
        os.replace(provisoire, fichier)
    except OSError as erreur:
        logger.warning("%s non ecrit (%s) : le travail continue.", quoi, erreur)
        return False
    return True
