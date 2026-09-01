"""Un fichier de configuration relu quand il change, jamais avant.

Ecrit apres avoir trouve **quatre** fois la meme forme de defaut dans la nuit
du 01/09/2026 : une valeur lue une fois, a la construction d'un objet
lui-meme cree au demarrage du serveur, puis servie comme si elle etait
actuelle.

| Ou | Ce que ca donnait |
|---|---|
| Sonde Docker du bac a sable | un Docker lance apres ARENA restait invisible |
| Grille de prix du plaquiste | un prix modifie n'etait vu qu'au redemarrage |
| Politique de permissions | une regle **durcie** n'etait pas appliquee |
| `PermissionManager` | idem, sur les neuf booleens |

Trois des quatre concernent un fichier sur le disque, et c'est ce que ce
module partage : la relecture se declenche sur la **date de modification**,
jamais sur une horloge. Un fichier inchange n'est pas relu ; un fichier
change l'est au premier usage qui suit.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Generic, Optional, TypeVar

logger = logging.getLogger("usman.fichier_suivi")

T = TypeVar("T")


def date_de(chemin: Path) -> Optional[float]:
    """Date de derniere modification, `None` si le fichier est absent.

    `None` n'est pas `0` : un fichier absent n'a pas de date, il n'a pas la
    date zero. La distinction compte — c'est cette valeur qui decide d'une
    relecture, et `0` la declencherait une seule fois puis plus jamais.
    """
    try:
        return chemin.stat().st_mtime
    except OSError:
        return None


class FichierSuivi(Generic[T]):
    """Le contenu d'un fichier, relu quand sa date de modification change.

    `lecteur` recoit le chemin et rend ce qu'il veut. Il doit **toujours
    rendre quelque chose** — un fichier absent ou illisible se traduit par une
    valeur vide, jamais par une exception qui figerait l'ancien contenu :
    servir une configuration disparue est plus dangereux que servir une
    configuration vide, parce que la disparition ne se remarque pas.
    """

    def __init__(self, chemin: Path, lecteur: Callable[[Path], T],
                 nom: str = "") -> None:
        self.chemin = Path(chemin)
        self._lecteur = lecteur
        self._nom = nom or self.chemin.name
        self._valeur = lecteur(self.chemin)
        self._date = date_de(self.chemin)

    def actuel(self) -> T:
        """Le contenu a jour. Relit le fichier si sa date a change."""
        date = date_de(self.chemin)
        if date != self._date:
            self._valeur = self._lecteur(self.chemin)
            self._date = date
            logger.info("%s relu (%s).", self._nom,
                        "fichier absent" if date is None else "fichier modifie")
        return self._valeur
