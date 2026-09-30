"""Agent de transformation photographique, distinct de l'analyse visuelle."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from apps.backend.pieces_jointes import DepotPiecesJointes
from core.restoration.codeformer import ErreurRestauration, ServiceCodeFormer

logger = logging.getLogger("usman.agent.image_restoration")

_FIDELITE = re.compile(
    r"\b(?:fidelit[eé]|fidelity)\s*(?:=|:|à|a)?\s*([-+]?\d+(?:[.,]\d+)?)\b",
    re.IGNORECASE,
)
_FOND = (
    "ameliore le fond", "améliore le fond", "ameliore l'arriere-plan",
    "améliore l'arrière-plan", "ameliore l arrière-plan", "enhance the background",
    "improve the background", "restaure le fond", "restaure l'arrière-plan",
)


def parametres_de_restauration(demande: str) -> tuple[float, bool]:
    """Les deux seuls controles produit exposes dans la conversation."""
    correspondance = _FIDELITE.search(demande or "")
    fidelity = float(correspondance.group(1).replace(",", ".")) if correspondance else 0.5
    fond = any(expression in (demande or "").lower() for expression in _FOND)
    return fidelity, fond


class ImageRestorationAgent:
    """Adapte une piece jointe autorisee au service CodeFormer local."""

    identifiant = "image_restoration"
    name = "ImageRestorationAgent"
    description = "Restaure une photo degradee et les details des visages avec CodeFormer."
    competences = ("restauration photo", "portrait abime", "amelioration de visage", "CodeFormer")

    def __init__(self, service: ServiceCodeFormer, pieces_jointes: DepotPiecesJointes):
        self.service = service
        self.pieces_jointes = pieces_jointes

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        identifiants = list((context or {}).get("attachments") or [])
        images = []
        for identifiant in identifiants:
            piece = self.pieces_jointes.lire(str(identifiant))
            if piece is not None and piece.est_image:
                images.append(piece)
        if not images:
            return {
                "status": "error", "agent": self.name,
                "response": "Je ne vois aucune image jointe autorisee a restaurer.",
            }
        if len(images) > 1:
            return {
                "status": "error", "agent": self.name,
                "response": "Joins une seule image par restauration pour garder un rendu et une provenance sans ambiguite.",
            }

        fidelity, fond = parametres_de_restauration(user_input)
        piece = images[0]
        original = piece.octets_originaux()
        if original is None:
            return {"status": "error", "agent": self.name,
                    "response": "Les octets originaux de cette image ne sont plus disponibles."}
        try:
            resultat = await self.service.restaurer(
                original, nom_source=piece.nom, fidelity=fidelity,
                background_enhancement=fond,
            )
        except ErreurRestauration as erreur:
            logger.info("Restauration refusee ou indisponible : %s", erreur)
            return {"status": "error", "agent": self.name, "response": str(erreur)}
        except Exception as erreur:  # noqa: BLE001 — frontiere d'un moteur optionnel
            logger.exception("Echec inattendu de la restauration CodeFormer")
            return {
                "status": "error", "agent": self.name,
                "response": f"La restauration a echoue ({type(erreur).__name__}). L'original est intact.",
            }

        avertissement = (
            " Execution sur CPU : elle peut etre tres lente."
            if resultat.device == "cpu" else ""
        )
        return {
            "status": "success",
            "agent": self.name,
            "response": (
                "Photo restauree avec CodeFormer. L'original n'a pas ete modifie."
                f" Fidelity : {resultat.fidelity:.2f}."
                + (" Arriere-plan ameliore avec Real-ESRGAN." if fond else "")
                + avertissement
            ),
            "restoration": resultat.to_dict(),
            # Reutilise le contrat d'artefact existant de la PWA : le rendu
            # apparait comme un fichier ouvrable, pas comme un chemin de chat.
            "document": {
                "statut": "SUCCESS",
                "url": resultat.url,
                "message": "Image restauree",
                "type": "image/png",
            },
        }
