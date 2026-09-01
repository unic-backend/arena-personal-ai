"""Purge des artefacts vidéo générés trop anciens.

Trouvé à l'audit du 01/09/2026 (DEC-0037) : `data/montages/` et
`media/rendered/` accumulent indéfiniment — aucun TTL, aucune purge,
contrairement aux pièces jointes entrantes qui expirent bien
(`apps/backend/pieces_jointes.py`). Même principe appliqué ici : « ce qui
n'est plus frais n'est plus servi ».

Purge PARESSEUSE, comme `DepotPiecesJointes.purger()` — appelée juste avant
d'écrire un nouveau rendu, jamais par une tâche planifiée séparée : pas
d'infrastructure de cron à maintenir pour ça, et un dossier jamais réécrit
ne grossit jamais non plus, sans purge inutile.
"""
import logging
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("usman.video.nettoyage")

#: 30 jours — assez pour retrouver un rendu récent, pas assez pour
#: accumuler indéfiniment sur un disque qui n'est pas infini.
AGE_MAX_SECONDES = 30 * 24 * 3600


def purger_artefacts_anciens(
    dossier: Path, age_max_secondes: float = AGE_MAX_SECONDES,
    maintenant: Optional[float] = None,
) -> List[str]:
    """Retire les fichiers de `dossier` plus vieux que `age_max_secondes`.

    Rend la liste des chemins retirés — jamais silencieux. Un dossier
    absent n'est pas une erreur : rien à purger. Un fichier qui refuse
    d'être retiré (permission, verrou) est signalé et laissé en place,
    jamais une exception qui empêcherait le nouveau rendu d'être écrit.
    """
    if not dossier.is_dir():
        return []
    limite = (maintenant if maintenant is not None else time.time()) - age_max_secondes
    retires: List[str] = []
    for fichier in sorted(dossier.iterdir()):
        if not fichier.is_file():
            continue
        try:
            if fichier.stat().st_mtime < limite:
                fichier.unlink()
                retires.append(str(fichier))
        except OSError as erreur:
            logger.warning("Purge : %s non retiré (%s)", fichier, erreur)
    if retires:
        logger.info("Purge : %d artefact(s) retiré(s) de %s", len(retires), dossier)
    return retires
