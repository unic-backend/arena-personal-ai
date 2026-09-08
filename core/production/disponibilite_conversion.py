"""Ce que la capacité `file_conversion` sait réellement faire sur cette
machine — mesuré par la sonde du connecteur, jamais deviné.

Même discipline que `disponibilite_swe.py` (DEC-0073) : un seul endroit
mesure, personne d'autre ne peut diverger de ce qu'il rapporte.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.connectors.base import EtatSante
from core.production.conversion.registre import matrice_disponibilite


async def disponibilite_conversion(connecteur_file_conversion: Optional[Any]) -> Dict[str, Any]:
    """L'état de la capacité, et le détail des couples de formats.

    Args:
        connecteur_file_conversion: le `ConnecteurFileConversion` construit,
            ou `None` s'il n'a pas pu être obtenu du registre.

    Returns:
        `{disponible, raison, formats}` — `formats` vient directement de
        `formats_disponibles()`, jamais recalculé ici.
    """
    if connecteur_file_conversion is None:
        return {"disponible": False, "raison": "connecteur non construit", "formats": []}

    try:
        sante = connecteur_file_conversion.sonder()
    except Exception as erreur:  # noqa: BLE001 — un rapport ne meurt pas d'une sonde en echec
        return {"disponible": False, "raison": f"sonde en echec : {type(erreur).__name__}",
                "formats": []}

    if sante.etat is not EtatSante.OPERATIONNEL:
        raison = sante.message or sante.etat.value
        if sante.ce_qui_manque:
            raison = f"{raison} ({sante.ce_qui_manque})"
        return {"disponible": False, "raison": raison, "formats": []}

    # La matrice directement, jamais via `.executer()` : passer par les
    # permissions pour une simple lecture de capacité pourrait rendre
    # `A_CONFIRMER`/`REFUSE` selon la config du proprietaire, et ce rapport
    # de disponibilité mentirait alors sur ce que la machine sait faire.
    return {"disponible": True, "raison": "", "formats": matrice_disponibilite()}
