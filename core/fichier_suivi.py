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
module partage : la relecture se declenche sur l'**etat du fichier**, jamais
sur une horloge. Un fichier inchange n'est pas relu ; un fichier change l'est
au premier usage qui suit.

**La date seule ne suffit pas** (mesure du 29/09/2026). Elle a suffi
jusque-la, et c'est ce qui rend le defaut dangereux : deux ecritures
successives peuvent porter exactement la meme date de modification, parce que
la granularite de l'horodatage appartient au systeme de fichiers, pas a
Python. Mesure directe, deux ecritures a la suite :

    ecriture 1 -> st_mtime_ns = 1790716950743122667
    ecriture 2 -> st_mtime_ns = 1790716950743122667   (identique)

Le fichier avait change, la date non, la relecture n'avait pas lieu. Sous
ext4 avec des ecritures espacees, ca n'arrive quasiment jamais — donc la CI ne
pouvait pas le voir. Sur un partage reseau, un volume monte depuis Windows ou
un systeme de fichiers a granularite seconde, ca arrive. Et ce que ca laissait
passer est precisement ce que ce module existe pour empecher : une **regle de
permission durcie qui n'est pas appliquee** (`core/permissions/politique.py`,
`core/permissions/permission_manager.py`), ou un **prix modifie qui n'est pas
vu au chiffrage suivant** (`agents/plaquiste/plaquiste_agent.py`) — un mauvais
prix sur un document qui part chez un client.

La comparaison porte donc sur `empreinte_de()` : date, taille, inode **et une
empreinte du contenu**. Les trois premiers champs ne suffisaient pas non plus
— mesure du meme jour, sur les deux cas reels du depot : remplacer `4500` par
`5200` dans `config/metier.yaml`, ou `allowed` par `denied` dans
`config/permissions.yaml`, ne change **ni** la date, **ni** la taille, **ni**
l'inode. Les deux changements qui comptent le plus dans ce depot — un prix et
une interdiction — sont exactement ceux qui echappaient a une comparaison de
metadonnees.

Lire le contenu pour le hacher coute **22 us** sur `config/metier.yaml`
(8,5 Ko, mesure du 29/09/2026) contre **7,9 ms** pour le `yaml.safe_load` que
ca evite : 360 fois moins cher que la relecture qu'on cherche a ne pas faire.
La promesse du module tient donc toujours — un fichier inchange n'est pas
**relu**, au sens ou son `lecteur` (parse, validation, construction d'objets)
n'est pas rappele. Au-dela de `PLAFOND_CONTENU`, on ne lit plus : un gros
fichier retombe sur les metadonnees seules, ou la fenetre d'angle mort est
negligeable devant le cout d'une lecture integrale a chaque appel.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable, Generic, Optional, Tuple, TypeVar

logger = logging.getLogger("usman.fichier_suivi")

T = TypeVar("T")

#: Ce qu'on compare : (date en ns, taille, inode, empreinte du contenu).
#: Le dernier champ est `None` au-dela de `PLAFOND_CONTENU`.
Empreinte = Tuple[int, int, int, Optional[bytes]]

#: Au-dela de cette taille, on ne lit plus le contenu pour le comparer.
#:
#: Ce module suit des fichiers de **configuration** : le plus gros du depot
#: est `config/permissions_services.yaml`, 27 Ko. Une marge de deux ordres de
#: grandeur laisse la place a leur croissance sans jamais lire un fichier dont
#: la lecture couterait vraiment quelque chose. Au-dessus, la comparaison
#: retombe sur les metadonnees seules — moins sur, mais un fichier de cette
#: taille n'est pas ce que ce module est fait pour suivre.
PLAFOND_CONTENU = 4 * 1024 * 1024


def date_de(chemin: Path) -> Optional[float]:
    """Date de derniere modification, `None` si le fichier est absent.

    `None` n'est pas `0` : un fichier absent n'a pas de date, il n'a pas la
    date zero. La distinction compte — c'est cette valeur qui decide d'une
    relecture, et `0` la declencherait une seule fois puis plus jamais.

    **Ce n'est plus ce qui decide d'une relecture** : `empreinte_de()` l'est
    (voir l'en-tete du module). Cette fonction reste le point d'entree pour
    qui veut *afficher* ou *journaliser* une date — ce qu'en fait
    `agents/plaquiste/plaquiste_agent.py:date_du_metier()`. L'utiliser pour
    detecter un changement rouvre le defaut du 29/09/2026.
    """
    try:
        return chemin.stat().st_mtime
    except OSError:
        return None


def empreinte_de(chemin: Path) -> Optional[Empreinte]:
    """Etat du fichier tel qu'on le compare : date, taille, inode, contenu.

    `None` si le fichier est absent, pour la meme raison que `date_de` : un
    fichier absent n'a pas d'etat, et un etat « zero » ne se distinguerait pas
    d'un fichier vide.

    Les quatre champs attrapent quatre choses differentes, et c'est pour ca
    qu'ils sont tous les quatre la :

    - `st_mtime_ns` — le cas courant, une ecriture apres un delai.
    - `st_size` — deux ecritures dans le meme tic d'horloge du systeme de
      fichiers, de longueurs differentes. La date ne bouge pas, la taille si.
    - `st_ino` — la reecriture atomique (ecrire a cote, puis remplacer), qui
      est la maniere dont ce depot ecrit ses fichiers d'etat
      (`core/production/journal_projet.py`). Le nouveau fichier peut avoir la
      taille et la date de l'ancien ; il n'a pas son inode.
    - le **contenu** — le seul qui voit `4500` devenir `5200` ou `allowed`
      devenir `denied` : meme date, meme taille, meme inode. Les deux cas
      reels du depot.

    Le hachage n'est pas cryptographique par besoin de securite : personne ne
    cherche ici a resister a une collision fabriquee, le fichier est local et
    deja de confiance. BLAKE2b tronque a 16 octets est simplement rapide et
    sans collision accidentelle a cette echelle.

    Un fichier illisible (droits, disparition entre le `stat` et la lecture)
    ne leve pas : il rend une empreinte de contenu `None`, donc se compare sur
    ses seules metadonnees. Lever ici figerait l'ancienne valeur — exactement
    le defaut que ce module existe pour empecher.
    """
    try:
        etat = chemin.stat()
    except OSError:
        return None

    contenu: Optional[bytes] = None
    if etat.st_size <= PLAFOND_CONTENU:
        try:
            contenu = hashlib.blake2b(chemin.read_bytes(), digest_size=16).digest()
        except OSError:
            contenu = None
    return (etat.st_mtime_ns, etat.st_size, etat.st_ino, contenu)


class FichierSuivi(Generic[T]):
    """Le contenu d'un fichier, relu quand le fichier change.

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
        self._empreinte = empreinte_de(self.chemin)

    def actuel(self) -> T:
        """Le contenu a jour. Relit le fichier si son empreinte a change."""
        empreinte = empreinte_de(self.chemin)
        if empreinte != self._empreinte:
            self._valeur = self._lecteur(self.chemin)
            self._empreinte = empreinte
            logger.info("%s relu (%s).", self._nom,
                        "fichier absent" if empreinte is None else "fichier modifie")
        return self._valeur
