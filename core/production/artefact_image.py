"""Un fichier n'est pas une preuve — l'image qu'il contient l'est.

Mission ARENA x HIDREAM-I1 (DEC-0085). « Generation terminee » ou un nom de
fichier rendu par un moteur ne prouvent rien : ce module OUVRE l'image et
verifie qu'elle existe reellement, qu'elle n'est pas tronquee, et qu'elle a
les dimensions demandees — la meme discipline que
`core/connectors/xaar_kaname.py` (« un code de retour 0 ne prouve pas qu'un
fichier a ete produit ») appliquee au CONTENU du fichier, pas seulement a sa
presence.

Reutilise Pillow, deja une dependance d'ARENA
(`core/connectors/media_metadata.py`) — aucune bibliotheque d'image de
plus.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger("usman.production.artefact_image")

#: En dessous de ce poids, un fichier « image » n'est presque surement
#: qu'un en-tete tronque — pas une vraie photo, meme a basse resolution.
TAILLE_MINIMALE_OCTETS = 512


@dataclass
class ValidationImage:
    """Ce qui a ete reellement verifie sur un fichier — jamais suppose."""

    valide: bool
    raison: str
    largeur: Optional[int] = None
    hauteur: Optional[int] = None
    format: Optional[str] = None
    taille_octets: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valide": self.valide, "raison": self.raison, "largeur": self.largeur,
            "hauteur": self.hauteur, "format": self.format, "taille_octets": self.taille_octets,
        }


def valider_image(
    chemin: Path,
    *,
    largeur_attendue: Optional[int] = None,
    hauteur_attendue: Optional[int] = None,
    taille_minimale_octets: int = TAILLE_MINIMALE_OCTETS,
) -> ValidationImage:
    """Ouvre reellement `chemin` et verifie que c'est une image utilisable.

    Args:
        chemin: le fichier a verifier.
        largeur_attendue/hauteur_attendue: si fournies, la dimension REELLE
            doit correspondre exactement — un moteur qui rend une taille
            differente de celle demandee est une erreur, pas un detail.
        taille_minimale_octets: en dessous, refuse avant meme d'ouvrir
            l'image (un fichier de quelques octets ne peut pas etre une
            image reelle, quel que soit son en-tete).

    Returns:
        Une `ValidationImage` — `valide=False` porte toujours sa raison en
        clair, jamais une exception qui remonterait a l'appelant.
    """
    if not chemin.is_file():
        return ValidationImage(False, f"fichier absent : {chemin}")

    taille = chemin.stat().st_size
    if taille < taille_minimale_octets:
        return ValidationImage(
            False, f"fichier trop petit ({taille} octets, minimum {taille_minimale_octets}) "
                  "— probablement tronque ou vide", taille_octets=taille)

    try:
        with Image.open(chemin) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as erreur:
        return ValidationImage(
            False, f"image illisible ou corrompue : {type(erreur).__name__} : {erreur}",
            taille_octets=taille)

    # `verify()` ferme le fichier une fois la verification faite (documente
    # par Pillow) : une seconde ouverture est necessaire pour lire les
    # dimensions et le format d'une image dont on sait deja qu'elle est
    # valide.
    try:
        with Image.open(chemin) as image:
            largeur, hauteur = image.size
            format_image = image.format
    except (UnidentifiedImageError, OSError, ValueError) as erreur:
        return ValidationImage(
            False, f"image verifiee mais illisible a la relecture : {erreur}", taille_octets=taille)

    if largeur <= 0 or hauteur <= 0:
        return ValidationImage(False, f"dimensions non exploitables ({largeur}x{hauteur})",
                               largeur=largeur, hauteur=hauteur, taille_octets=taille)

    if largeur_attendue is not None and largeur != largeur_attendue:
        return ValidationImage(
            False, f"largeur {largeur} differente de celle demandee ({largeur_attendue})",
            largeur=largeur, hauteur=hauteur, format=format_image, taille_octets=taille)
    if hauteur_attendue is not None and hauteur != hauteur_attendue:
        return ValidationImage(
            False, f"hauteur {hauteur} differente de celle demandee ({hauteur_attendue})",
            largeur=largeur, hauteur=hauteur, format=format_image, taille_octets=taille)

    return ValidationImage(True, "image valide", largeur=largeur, hauteur=hauteur,
                           format=format_image, taille_octets=taille)


@dataclass
class ProvenanceImage:
    """Ce que la mission §14 demande de conserver — jamais moins."""

    modele: str
    modele_version: str
    fournisseur: str
    seed: Optional[int] = None
    largeur: int = 0
    hauteur: int = 0
    duree_generation_s: Optional[float] = None
    prompt: str = ""
    genere_le: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "modele": self.modele, "modele_version": self.modele_version,
            "fournisseur": self.fournisseur, "seed": self.seed,
            "largeur": self.largeur, "hauteur": self.hauteur,
            "duree_generation_s": self.duree_generation_s, "prompt": self.prompt,
            "genere_le": self.genere_le,
        }


def ecrire_provenance(chemin_image: Path, provenance: ProvenanceImage) -> Path:
    """Un fichier `.json` a cote de l'image — jamais dans l'image elle-meme
    (les metadonnees EXIF/PNG-text ne survivent pas toujours a un futur
    traitement, un sidecar si). Retourne le chemin ecrit."""
    chemin_json = chemin_image.with_suffix(chemin_image.suffix + ".json")
    chemin_json.write_text(
        json.dumps(provenance.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin_json


def lire_provenance(chemin_image: Path) -> Optional[Dict[str, Any]]:
    """Relit le sidecar de provenance — `None` s'il n'existe pas ou est
    illisible, jamais une exception."""
    chemin_json = chemin_image.with_suffix(chemin_image.suffix + ".json")
    try:
        return json.loads(chemin_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        logger.info("Provenance illisible pour %s : %s", chemin_image, erreur)
        return None
