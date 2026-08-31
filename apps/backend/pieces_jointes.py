"""Les pieces jointes envoyees depuis l'interface : lues, puis effacees.

Son application televerse les fichiers avant d'envoyer le message. Jusqu'ici
ARENA repondait `501` : aucune chaine ne les lisait. Le lecteur existait
pourtant (`tools/documents/reader.py`, PDF, DOCX, TXT, MD, CSV) — il n'etait
simplement pas relie.

Une image suit un chemin different : `tools/documents/reader.py` sert
LightRAG et GraphRAG, qui n'acceptent que du texte — y ajouter des extensions
d'image ferait tenter de « lire » une photo comme un document. Une image ne
passe donc jamais par ce lecteur ; elle est encodee ici et confiee telle
quelle a `VisionAgent` (DEC-0019), qui parle au modele de vision.

**Quatre regles, et la premiere est une regle de vie privee :**

1. **Le fichier est efface des qu'il est lu.** Seul son texte — ou, pour une
   image, ses octets encodes — reste, en memoire, pour la duree d'une
   conversation. Ses devis, ses plans et ses courriers de clients ne
   s'accumulent pas dans un dossier que personne ne surveille.

2. **Le contenu d'une piece jointe est une donnee, jamais une consigne.** Un
   document peut contenir la phrase « ignore tes instructions ». Il est annonce
   comme du contenu de fichier, pas comme une instruction du proprietaire.

3. **Un format non lu le dit.** `NON_PRIS_EN_CHARGE` avec la liste des formats
   lus. Accepter un fichier et rendre un identifiant qui ne mene a rien serait
   la meme faute que le connecteur qui se disait « publie ».

4. **Ce qui n'est plus frais n'est plus servi.** Les textes expirent ; une piece
   jointe d'hier ne doit pas revenir dans la conversation d'aujourd'hui.
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

# Taille maximale d'un fichier accepte. Reglable : elle depend de sa machine.
TAILLE_MAX_OCTETS = int(os.getenv("USMAN_MAX_FILE_MB", "25")) * 1024 * 1024

# Formats d'image reconnus. Une image n'est jamais ecrite sur le disque : ses
# octets sont encodes directement en memoire, comme le texte l'est pour un
# document — la meme regle de vie privee, appliquee au meme endroit.
EXTENSIONS_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Duree de vie du texte extrait. Assez pour une conversation, pas pour la
# journee : une piece jointe d'hier n'a rien a faire dans la question d'aujourd'hui.
DUREE_VIE_MINUTES = 60

# Plafond du texte conserve par piece. Un PDF de 400 pages ne rentre pas dans un
# prompt, et le tronquer en silence ferait croire qu'il a ete lu en entier.
CARACTERES_MAX = 40_000
MENTION_TRONQUE = "\n\n[…] Document tronque : seule cette partie a ete lue."


def nom_de_fichier_sur(nom: Optional[str]) -> str:
    """Ne garde que la derniere partie d'un nom venu du navigateur.

    `Path(...).name` ne suffit pas : sur Linux, le `\\` de Windows n'est pas un
    separateur, et « C:\\Users\\Saer\\secret.txt » revenait entier. Le
    proprietaire est sous Windows et son serveur sera sous Linux — les deux
    separateurs sont donc coupes explicitement.
    """
    brut = (nom or "").replace("\\", "/")
    dernier = Path(brut).name.strip()
    return dernier or "sans-nom"


@dataclass(frozen=True)
class PieceJointe:
    """Un fichier recu, son texte ou son image, et l'etat reel de sa lecture.

    `pdf_base64` suit la meme regle que `image_base64` — en memoire, jamais
    sur le disque au-dela de la lecture. Un PDF peut etre un plan de
    construction : `PlaquisteAgent` en a besoin, brievement, pour le confier a
    OpenTakeoff (un processus externe qui lit un vrai fichier). Le texte
    extrait (`texte`) reste la voie normale pour un devis ou un document.
    """

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
        """Ce que l'interface recoit. **Ni le texte ni l'image n'y sont** : ils
        ne feraient que des allers-retours inutiles sur le reseau, et ils
        contiennent ses documents ou ses photos."""
        return {
            "id": self.identifiant,
            "name": self.nom,
            "size": self.octets,
            "status": self.statut,
            "readable": self.lisible,
            # Distinct du `kind` que /files ajoute par-dessus (un indice fourni
            # par l'interface) : celui-ci est mesure, jamais declaratif.
            "nature": "image" if self.est_image else "document",
            "truncated": self.tronque,
            "reason": self.raison,
            "characters": len(self.texte),
        }


class DepotPiecesJointes:
    """Recoit un fichier, en extrait le texte, efface le fichier, garde le texte."""

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

    # --- Depot ----------------------------------------------------------------

    def _horodatages(self) -> tuple:
        maintenant = datetime.now(timezone.utc)
        return (
            maintenant.isoformat(timespec="seconds"),
            (maintenant + timedelta(minutes=self.duree_vie_minutes)).isoformat(timespec="seconds"),
        )

    def _refus(self, nom: str, octets: int, statut: str, raison: str) -> PieceJointe:
        depose, expire = self._horodatages()
        piece = PieceJointe(
            identifiant=uuid.uuid4().hex, nom=nom, octets=octets,
            statut=statut, raison=raison, depose_le=depose, expire_le=expire,
        )
        self._pieces[piece.identifiant] = piece
        logger.info("Piece jointe refusee (%s) : %s — %s", statut, nom, raison)
        return piece

    def _deposer_image(self, nom_sur: str, contenu: bytes) -> PieceJointe:
        """Une image ne touche jamais le disque : ses octets sont encodes en
        memoire, directement — aucun lecteur externe n'en a besoin."""
        depose, expire = self._horodatages()
        piece = PieceJointe(
            identifiant=uuid.uuid4().hex, nom=nom_sur, octets=len(contenu),
            statut="LU", image_base64=base64.b64encode(contenu).decode("ascii"),
            depose_le=depose, expire_le=expire,
        )
        self._pieces[piece.identifiant] = piece
        logger.info("Piece jointe (image) lue : %s (%d octets).", nom_sur, len(contenu))
        return piece

    def refuser_trop_volumineux(self, nom: str) -> PieceJointe:
        """Refuse un envoi dont la taille depasse le plafond, sans l'avoir lu.

        Existe pour que l'appelant puisse s'arreter de lire DES QU'il a
        depasse le plafond, au lieu de charger tout l'envoi en memoire pour
        decouvrir ensuite qu'il etait trop gros (`deposer` mesure
        `len(contenu)`, donc apres coup).

        `octets=0` n'est pas une taille mesuree ici : elle ne l'a
        volontairement pas ete, et la raison le dit sans avancer de chiffre —
        un « 25,0 Mo » affiche pour un envoi de 2 Go serait faux.
        """
        return self._refus(
            nom_de_fichier_sur(nom), 0, "ECHEC",
            f"fichier trop volumineux : depasse le maximum de "
            f"{self.taille_max / 1024**2:.0f} Mo",
        )

    def deposer(self, nom: str, contenu: bytes) -> PieceJointe:
        """Lit le fichier et n'en garde que le texte, ou l'image encodee.
        Le fichier est efface.

        Ne leve jamais : un fichier illisible rend une piece portant son statut
        et sa raison. L'interface doit pouvoir l'afficher, pas se casser dessus.
        """
        nom_sur = nom_de_fichier_sur(nom)
        extension = Path(nom_sur).suffix.lower()

        if extension in EXTENSIONS_IMAGE:
            if len(contenu) > self.taille_max:
                return self._refus(
                    nom_sur, len(contenu), "ECHEC",
                    f"fichier trop volumineux ({len(contenu) / 1024**2:.1f} Mo, "
                    f"maximum {self.taille_max / 1024**2:.0f} Mo)",
                )
            return self._deposer_image(nom_sur, contenu)

        if extension not in EXTENSIONS_LISIBLES:
            lisibles = ", ".join(sorted(EXTENSIONS_LISIBLES | EXTENSIONS_IMAGE))
            return self._refus(
                nom_sur, len(contenu), "NON_PRIS_EN_CHARGE",
                f"format {extension or 'sans extension'} ; formats lus : {lisibles}",
            )

        if len(contenu) > self.taille_max:
            return self._refus(
                nom_sur, len(contenu), "ECHEC",
                f"fichier trop volumineux ({len(contenu) / 1024**2:.1f} Mo, "
                f"maximum {self.taille_max / 1024**2:.0f} Mo)",
            )

        dossier = Path(tempfile.mkdtemp(prefix="arena-piece-"))
        chemin = dossier / nom_sur
        try:
            chemin.write_bytes(contenu)
            document = lire_document(chemin, taille_max=self.taille_max)
        except Exception as souci:  # noqa: BLE001 - un fichier casse n'arrete rien
            logger.error("Lecture impossible (%s) : %s", nom_sur, souci)
            return self._refus(nom_sur, len(contenu), "ECHEC", str(souci))
        finally:
            # Le fichier disparait, lu ou non. C'est la regle de vie privee.
            chemin.unlink(missing_ok=True)
            dossier.rmdir()

        texte = document.texte
        tronque = len(texte) > self.caracteres_max
        if tronque:
            texte = texte[: self.caracteres_max] + MENTION_TRONQUE

        depose, expire = self._horodatages()
        piece = PieceJointe(
            identifiant=uuid.uuid4().hex, nom=nom_sur, octets=len(contenu),
            statut=document.statut, texte=texte, raison=document.raison,
            # Un PDF peut etre un plan : ses octets restent en memoire (deja
            # la, `contenu` — aucune relecture du disque), au cas ou
            # `PlaquisteAgent` en a besoin pour OpenTakeoff.
            pdf_base64=base64.b64encode(contenu).decode("ascii") if extension == ".pdf" else "",
            tronque=tronque, depose_le=depose, expire_le=expire,
        )
        self._pieces[piece.identifiant] = piece
        logger.info("Piece jointe lue : %s (%s caracteres, statut %s).",
                    nom_sur, len(texte), document.statut)
        return piece

    # --- Lecture --------------------------------------------------------------

    def lire(self, identifiant: str) -> Optional[PieceJointe]:
        """La piece, ou None si elle est inconnue ou perimee."""
        piece = self._pieces.get(identifiant)
        if piece is None:
            return None
        if piece.est_perimee():
            self._pieces.pop(identifiant, None)
            return None
        return piece

    def purger(self) -> int:
        """Retire les pieces perimees. Rend combien ont ete retirees."""
        perimees = [ident for ident, piece in self._pieces.items() if piece.est_perimee()]
        for ident in perimees:
            self._pieces.pop(ident, None)
        return len(perimees)

    def nombre(self) -> int:
        """Combien de pieces sont encore vivantes."""
        self.purger()
        return len(self._pieces)
