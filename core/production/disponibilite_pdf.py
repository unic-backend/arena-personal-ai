"""Ce que la capacité `pdf` sait réellement faire — mesuré par la sonde du
connecteur, jamais deviné.

Même discipline que `disponibilite_conversion.py` (DEC-0074) et
`disponibilite_organisation.py` (DEC-0075).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.connectors.base import EtatSante


async def disponibilite_pdf(connecteur_pdf: Optional[Any]) -> Dict[str, Any]:
    """`{disponible, raison}` — jamais supposé disponible parce qu'un objet existe."""
    if connecteur_pdf is None:
        return {"disponible": False, "raison": "connecteur non construit"}

    try:
        sante = connecteur_pdf.sonder()
    except Exception as erreur:  # noqa: BLE001 — un rapport ne meurt pas d'une sonde en echec
        return {"disponible": False, "raison": f"sonde en echec : {type(erreur).__name__}"}

    if sante.etat is not EtatSante.OPERATIONNEL:
        raison = sante.message or sante.etat.value
        if sante.ce_qui_manque:
            raison = f"{raison} ({sante.ce_qui_manque})"
        return {"disponible": False, "raison": raison}

    return {"disponible": True, "raison": ""}
