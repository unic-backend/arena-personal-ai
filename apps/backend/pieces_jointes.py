"""Les pieces jointes envoyees depuis l'interface : lues, puis effacees.

Les documents texte passent par le lecteur documentaire. Les images suivent un
chemin separe : elles restent en memoire et sont confiees au VisionAgent.

Regles :
- aucun fichier utilisateur ne persiste sur disque apres lecture ;
- le contenu d'une piece jointe est une donnee, jamais une instruction ;
- un format non pris en charge est annonce explicitement ;
- une piece expiree n'est plus servie ;
- une extension d'image ne suffit jamais : les octets doivent correspondre a
  un vrai format d'image accepte avant d'etre transmis au modele de vision.
"""
import base64
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from tools.documents.reader import EXTENSIONS_LISIBLES, lire_document

logger = logging.getLogger("usman.backend.pieces")

TAILLE_MAX_OCTETS = int(os.getenv("USMAN_MAX_FILE_MB", "25")) * 1024 * 1024
EXTENSIONS_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DUREE_VIE_MINUTES = 60
CARACTERES_MAX = 40_000
MENTION_TRONQUE = "\n\n[…] Document tronque : seule cette partie a ete lue."


def nom_de_fichier_sur(nom: Optional[str]) -> str:
    brut = (nom or "").replace("\\", "/")
    dernier = Path(brut).name.strip()
    return dernier or "sans-nom"


def _format_image_reel(contenu: bytes) -> Optional[str]:
    """Detecte les formats d'image autorises a partir de leurs signatures.

    La detection est volontairement locale et sans ecriture disque. Elle evite
    qu'un executable ou un document renomme en ``photo.png`` soit marque LU et
    envoye tel quel au modele de vision.
    """
    if contenu.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if contenu.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if contenu.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(contenu) >= 12 and contenu[:4] == b"RIFF" and contenu[8:12] == b"WEBP":
        return ".webp"
    return None


def _extension_compatible_image(extension: str, format_reel: str) -> bool:
    if extension in {".jpg", ".jpeg"}:
        return format_reel == ".jpg"
    return extension == format_reel


@dataclass(frozen=True)
class PieceJointe:
    identifiant: str
    nom: str
    octets: int
    statut: str
    texte: str = ""
    image_base64: str = ""
    pdf_base64: str = ""
    raison: Optional[str] = None
    tronque: bool = False
    depose_le: str = ""
    expire_le: str = ""

    @property
    def est_image(self) -> bool:
        return bool(self.image_base64)

    @property
    def lisible(self) -> bool:
        return self.statut == "LU" and (bool(self.texte.strip()) or self.est_image)

    def est_perimee(self, maintenant: Optional[datetime] = None) -> bool:
        if not self.expire_le:
            return False
        try:
            limite = datetime.fromisoformat(self.expire_le)
        except ValueError:
            return True
        return (maintenant or datetime.now(timezone.utc)) >= limite

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.identifiant,
            "name": self.nom,
            "size": self.octets,
            "status": self.statut,
            "readable": self.lisible,
            "nature": "image" if self.est_image else "document",
            "truncated": self.tronque,
            "reason": self.raison,
            "characters": len(self.texte),
        }


class DepotPiecesJointes:
    def __init__(
        self,
        taille_max: int = TAILLE_MAX_OCTETS,
        duree_vie_minutes: int = DUREE_VIE_MINUTES,
        caracteres_max: int = CARACTERES_MAX,
    ) -> None:
        self.taille_max = taille_max
        self.duree_vie_minutes = duree_vie_minutes
        self.caracteres_max = caracteres_max
        self._pieces: Dict[str, PieceJointe] = {}

    def _horodatages(self) -> tuple:
        maintenant = datetime.now(timezone.utc)
        return (
            maintenant.isoformat(timespec="seconds"),
            (maintenant + timedelta(minutes=self.duree_vie_minutes)).isoformat(timespec="seconds"),
        )

    def _refus(self, nom: str, octets: int, statut: str, raison: str) -> PieceJointe:
        depose, expire = self._horodatages()
        piece = PieceJointe(
            identifiant=uuid.uuid4().hex,
            nom=nom,
            octets=octets,
            statut=statut,
            raison=raison,
            depose_le=depose,
            expire_le=expire,
        )
        self._pieces[piece.identifiant] = piece
        logger.info("Piece jointe refusee (%s) : %s — %s", statut, nom, raison)
        return piece

    def _deposer_image(self, nom_sur: str, contenu: bytes) -> PieceJointe:
        extension = Path(nom_sur).suffix.lower()
        format_reel = _format_image_reel(contenu)
        if format_reel is None:
            return self._refus(
                nom_sur,
                len(contenu),
                "ECHEC",
                "contenu image invalide : la signature du fichier ne correspond a aucun format image accepte",
            )
        if not _extension_compatible_image(extension, format_reel):
            return self._refus(
                nom_sur,
                len(contenu),
                "ECHEC",
                f"extension {extension} incoherente avec le contenu reel {format_reel}",
            )

        depose, expire = self._horodatages()
        piece = PieceJointe(
            identifiant=uuid.uuid4().hex,
            nom=nom_sur,
            octets=len(contenu),
            statut="LU",
            image_base64=base64.b64encode(contenu).decode("ascii"),
            depose_le=depose,
            expire_le=expire,
        )
        self._pieces[piece.identifiant] = piece
        logger.info("Piece jointe (image %s) lue : %s (%d octets).", format_reel, nom_sur, len(contenu))
        return piece

    def refuser_trop_volumineux(self, nom: str) -> PieceJointe:
        return self._refus(
            nom_de_fichier_sur(nom),
            0,
            "ECHEC",
            f"fichier trop volumineux : depasse le maximum de {self.taille_max / 1024**2:.0f} Mo",
        )

    def deposer(self, nom: str, contenu: bytes) -> PieceJointe:
        nom_sur = nom_de_fichier_sur(nom)
        extension = Path(nom_sur).suffix.lower()

        if extension in EXTENSIONS_IMAGE:
            if len(contenu) > self.taille_max:
                return self._refus(
                    nom_sur,
                    len(contenu),
                    "ECHEC",
                    f"fichier trop volumineux ({len(contenu) / 1024**2:.1f} Mo, maximum {self.taille_max / 1024**2:.0f} Mo)",
                )
            return self._deposer_image(nom_sur, contenu)

        if extension not in EXTENSIONS_LISIBLES:
            lisibles = ", ".join(sorted(EXTENSIONS_LISIBLES | EXTENSIONS_IMAGE))
            return self._refus(
                nom_sur,
                len(contenu),
                "NON_PRIS_EN_CHARGE",
                f"format {extension or 'sans extension'} ; formats lus : {lisibles}",
            )

        if len(contenu) > self.taille_max:
            return self._refus(
                nom_sur,
                len(contenu),
                "ECHEC",
                f"fichier trop volumineux ({len(contenu) / 1024**2:.1f} Mo, maximum {self.taille_max / 1024**2:.0f} Mo)",
            )

        dossier = Path(tempfile.mkdtemp(prefix="arena-piece-"))
        chemin = dossier / nom_sur
        try:
            chemin.write_bytes(contenu)
            document = lire_document(chemin, taille_max=self.taille_max)
        except Exception as souci:  # noqa: BLE001
            logger.error("Lecture impossible (%s) : %s", nom_sur, souci)
            return self._refus(nom_sur, len(contenu), "ECHEC", str(souci))
        finally:
            chemin.unlink(missing_ok=True)
            dossier.rmdir()

        texte = document.texte
        tronque = len(texte) > self.caracteres_max
        if tronque:
            texte = texte[: self.caracteres_max] + MENTION_TRONQUE

        depose, expire = self._horodatages()
        piece = PieceJointe(
            identifiant=uuid.uuid4().hex,
            nom=nom_sur,
            octets=len(contenu),
            statut=document.statut,
            texte=texte,
            raison=document.raison,
            pdf_base64=base64.b64encode(contenu).decode("ascii") if extension == ".pdf" else "",
            tronque=tronque,
            depose_le=depose,
            expire_le=expire,
        )
        self._pieces[piece.identifiant] = piece
        logger.info("Piece jointe lue : %s (%s caracteres, statut %s).", nom_sur, len(texte), document.statut)
        return piece

    def lire(self, identifiant: str) -> Optional[PieceJointe]:
        piece = self._pieces.get(identifiant)
        if piece is None:
            return None
        if piece.est_perimee():
            self._pieces.pop(identifiant, None)
            return None
        return piece

    def purger(self) -> int:
        perimees = [ident for ident, piece in self._pieces.items() if piece.est_perimee()]
        for ident in perimees:
            self._pieces.pop(ident, None)
        return len(perimees)

    def nombre(self) -> int:
        self.purger()
        return len(self._pieces)
