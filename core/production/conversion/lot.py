"""Convertir plusieurs fichiers sans faire attendre le chat.

Même patron que `core/connectors/suivi_video.py`, premier et jusqu'ici seul
autre usage réel de `core/execution/travaux.py` (`FileDeTravaux`) — mission
§6 : « sans bloquer inutilement le processus principal », pas un second
ordonnanceur. Une conversion de fichier bloque réellement le thread
(sous-processus LibreOffice/ffmpeg, décodage Pillow) ; `asyncio.to_thread`
la sort de la boucle asyncio le temps de l'appel, comme n'importe quelle
autre requête pourrait sinon en pâtir pendant tout le lot.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List

from core.actions.resultat import ResultatAction
from core.execution.travaux import EtatTravail, FileDeTravaux, Travail

logger = logging.getLogger("usman.production.conversion.lot")

#: Un lot plus grand que ça n'est pas soumis : mission §6, « 1000 fichiers »,
#: mais sans borne un lot pourrait occuper la file de fond indéfiniment pour
#: une seule demande. Assez large pour un usage réel, jamais illimité.
LOT_MAX_FICHIERS = 200


def lot_acceptable(chemins: List[str]) -> str:
    """Chaîne vide si le lot peut être soumis, sinon la raison du refus."""
    if not chemins:
        return "aucun fichier fourni"
    if len(chemins) > LOT_MAX_FICHIERS:
        return f"{len(chemins)} fichiers demandés, plafond {LOT_MAX_FICHIERS}"
    return ""


async def _executer_lot(
    convertir_un: Callable[[str, str], ResultatAction],
    travail: Travail, chemins: List[str], format_cible: str,
) -> Dict[str, Any]:
    """Le corps du travail de fond : un fichier à la fois, annulable entre deux."""
    resultats: List[Dict[str, Any]] = []
    for chemin in chemins:
        if travail.etat is EtatTravail.ANNULE:
            break
        resultat = await asyncio.to_thread(convertir_un, chemin, format_cible)
        resultats.append({"entree": chemin, **resultat.to_dict()})
        travail.faits += 1

    reussites = sum(1 for r in resultats if r.get("a_eu_lieu"))
    return {
        "resultats": resultats, "reussites": reussites,
        "total_traites": len(resultats), "total_demandes": len(chemins),
    }


def convertir_lot_en_fond(
    convertir_un: Callable[[str, str], ResultatAction],
    file: FileDeTravaux, chemins: List[str], format_cible: str,
) -> Travail:
    """Soumet le lot et rend la main immédiatement — `travail.faits/total`
    avance au fur et à mesure, `travail.resultat` porte le détail par
    fichier une fois `TERMINE`.

    Args:
        convertir_un: `(chemin, format_cible) -> ResultatAction` — la même
            logique qu'utilise la conversion à l'unité, jamais une seconde
            implémentation.
    """
    return file.soumettre(
        f"conversion en lot vers .{format_cible} ({len(chemins)} fichier(s))",
        lambda travail: _executer_lot(convertir_un, travail, chemins, format_cible),
        total=len(chemins), passer_le_travail=True,
    )
