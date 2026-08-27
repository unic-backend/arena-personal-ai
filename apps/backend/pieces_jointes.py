"""Les pieces jointes envoyees depuis l'interface : lues, puis effacees.

Son application televerse les fichiers avant d'envoyer le message. Jusqu'ici
ARENA repondait `501` : aucune chaine ne les lisait. Le lecteur existait
pourtant (`tools/documents/reader.py`, PDF, DOCX, TXT, MD, CSV) — il n'etait
simplement pas relie.

**Quatre regles, et la premiere est une regle de vie privee :**

1. **Le fichier est efface des qu'il est lu.** Seul son texte reste, en memoire,
   pour la duree d'une conversation. Ses devis, ses plans et ses courriers de
   clients ne s'accumulent pas dans un dossier que personne ne surveille.

2. **Le contenu d'une piece jointe est une donnee, jamais une consigne.** Un
   document peut contenir la phrase « ignore tes instructions ». Il est annonce
   comme du contenu de fichier, pas comme une instruction du proprietaire.

3. **Un format non lu le dit.** `NON_PRIS_EN_CHARGE` avec la liste des formats
   lus. Accepter un fichier et rendre un identifiant qui ne mene a rien serait
   la meme faute que le connecteur qui se disait « publie ».

4. **Ce qui n'est plus frais n'est plus servi.** Les textes expirent ; une piece
   jointe d'hier ne doit pas revenir dans la conversation d'aujourd'hui.
"""
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
    """Un fichier recu, son texte, et l'etat reel de sa lecture."""

    identifiant: str
    nom: str
    octets: int
    statut: str
    texte: str = ""
    raison: Optional[str] = None
    tronque: bool = False
    depose_le: str = ""
    expire_le: str = ""

    @property
    def lisible(self) -> bool:
        return self.statut == "LU" and bool(self.texte.strip())

    def est_perimee(self, maintenant: Optional[datetime] = None) -> bool:
        if not self.expire_le:
            return False
        try:
            limite = datetime.fromisoformat(self.expire_le)
        except ValueError:
            return True
        return (maintenant or datetime.now(timezone.utc)) >= limite

    def to_dict(self) -> Dict[str, Any]:
        """Ce que l'interface recoit. **Le texte n'y est pas** : il ne fait que
        des allers-retours inutiles sur le reseau, et il contient ses documents."""
        return {
            "id": self.identifiant,
            "name": self.nom,
            "size": self.octets,
            "status": self.statut,
            "readable": self.lisible,
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

    def deposer(self, nom: str, contenu: bytes) -> PieceJointe:
        """Lit le fichier et n'en garde que le texte. Le fichier est efface.

        Ne leve jamais : un fichier illisible rend une piece portant son statut
        et sa raison. L'interface doit pouvoir l'afficher, pas se casser dessus.
        """
        nom_sur = nom_de_fichier_sur(nom)
        extension = Path(nom_sur).suffix.lower()

        if extension not in EXTENSIONS_LISIBLES:
            lisibles = ", ".join(sorted(EXTENSIONS_LISIBLES))
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
