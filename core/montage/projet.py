"""Le projet de montage : une timeline editable, pas une commande ffmpeg.

Avant ce module, les outils video d'ARENA etaient des appels ponctuels — une
entree, une sortie, et rien entre les deux. `cut_video`, `burn_subtitles`,
`convert_to_vertical_9_16` : chacun sait faire une chose, aucun ne garde
d'etat. Impossible d'ajouter un logo PUIS des sous-titres PUIS de recadrer
sans reencoder trois fois, et impossible pour le proprietaire de revoir ce
que l'IA a decide avant de rendre.

Ce module apporte ce qui manquait : une **representation de projet**, qui se
lit, se modifie, se relit, et se rend.

**Le modele suit celui d'OpenCut classic** (`apps/web/src/timeline/types.ts`,
MIT) : une scene porte des pistes typees, chaque piste porte des elements
places dans le temps. C'est le role que l'audit lui assigne — reference
d'implementation, pas moteur (`docs/audits/opencut_audit.md`).

**Quatre regles :**

1. **Le temps est en millisecondes entieres.** Un flottant de secondes
   accumule l'erreur au fil des coupes ; a 30 im/s une image dure 33 ms, et
   deux coupes qui devraient se toucher finissent par se chevaucher d'un
   cheveu. OpenCut a le meme choix (`MediaTime`, en ticks).

2. **Un projet invalide se refuse a la construction.** Une duree negative,
   un clip qui deborde de sa source, une piste vide de type inconnu : le
   projet ne se construit pas. Un rendu qui part d'un projet incoherent
   produit une video fausse qui a l'air juste.

3. **Rien n'est rendu ici.** Ce module decrit ; `rendu.py` execute. La
   frontiere existe pour que le moteur de rendu soit remplacable — par la
   reecriture d'OpenCut le jour ou elle livre son Editor API.

4. **Tout se serialise.** Un projet est un dictionnaire JSON : le
   proprietaire peut le relire, l'IA peut le reprendre au tour suivant, et
   un montage interrompu ne repart pas de zero.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ErreurProjet(ValueError):
    """Un projet ou une operation qui ne tient pas debout."""


class TypePiste(str, Enum):
    """Les pistes qu'un montage sait porter.

    Volontairement plus etroit que celles d'OpenCut : `effect` et `graphic`
    y sont des pistes a part entiere, ici une image posee sur la piste
    IMAGE suffit — ARENA n'a ni moteur d'effets ni bibliotheque de
    stickers, et declarer une piste que rien ne sait rendre serait annoncer
    une capacite absente.
    """

    VIDEO = "video"
    IMAGE = "image"
    TEXTE = "texte"
    AUDIO = "audio"


#: Ce qu'une piste accepte comme elements. Un texte sur une piste audio n'a
#: aucun sens, et le dire ici evite de le decouvrir au rendu.
ELEMENTS_PAR_PISTE: Dict[TypePiste, tuple] = {
    TypePiste.VIDEO: ("video",),
    TypePiste.IMAGE: ("image",),
    TypePiste.TEXTE: ("texte",),
    TypePiste.AUDIO: ("audio",),
}


@dataclass
class Media:
    """Un fichier source importe dans le projet.

    `duree_ms` est `None` tant que personne ne l'a mesuree : une duree
    inconnue n'est pas une duree nulle. C'est `operations.importer_media`
    qui la mesure avec ffprobe, jamais ce module.
    """

    identifiant: str
    chemin: str
    genre: str  # "video" | "image" | "audio"
    duree_ms: Optional[int] = None
    largeur: Optional[int] = None
    hauteur: Optional[int] = None
    #: Le nom que le PLAN lui donne — « logo », « chantier » — pour pouvoir
    #: le citer sans connaitre l'identifiant genere a l'import.
    nom: str = ""

    def __post_init__(self) -> None:
        if self.genre not in ("video", "image", "audio"):
            raise ErreurProjet(f"genre de media inconnu : {self.genre!r}")
        if self.duree_ms is not None and self.duree_ms <= 0:
            raise ErreurProjet(f"duree de media non positive : {self.duree_ms}")


@dataclass
class Element:
    """Un element pose sur une piste, a un instant donne.

    `debut_ms` est sa place sur la timeline ; `coupe_debut_ms` est le point
    d'entree DANS la source. Les deux sont distincts : deplacer un clip ne
    doit pas changer ce qu'il montre.
    """

    identifiant: str
    genre: str
    debut_ms: int
    duree_ms: int
    media_id: Optional[str] = None
    coupe_debut_ms: int = 0
    contenu: str = ""              # le texte, pour un element "texte"
    proprietes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.duree_ms <= 0:
            raise ErreurProjet(
                f"un element de duree {self.duree_ms} ms ne se rend pas : "
                "une duree nulle ou negative n'est pas un clip")
        if self.debut_ms < 0:
            raise ErreurProjet(f"debut negatif sur la timeline : {self.debut_ms} ms")
        if self.coupe_debut_ms < 0:
            raise ErreurProjet(f"point d'entree negatif dans la source : {self.coupe_debut_ms} ms")
        if self.genre == "texte" and not self.contenu.strip():
            raise ErreurProjet("un element texte sans texte n'a rien a afficher")
        if self.genre in ("video", "image", "audio") and not self.media_id:
            raise ErreurProjet(f"un element {self.genre} sans media source")

    @property
    def fin_ms(self) -> int:
        """L'instant ou l'element quitte la timeline."""
        return self.debut_ms + self.duree_ms


@dataclass
class Piste:
    """Une piste : un type, et des elements ordonnes dans le temps."""

    identifiant: str
    type: TypePiste
    nom: str = ""
    elements: List[Element] = field(default_factory=list)
    muette: bool = False
    masquee: bool = False

    def __post_init__(self) -> None:
        self.type = TypePiste(self.type)
        for element in self.elements:
            self._verifier_le_genre(element)

    def _verifier_le_genre(self, element: Element) -> None:
        acceptes = ELEMENTS_PAR_PISTE[self.type]
        if element.genre not in acceptes:
            raise ErreurProjet(
                f"un element « {element.genre} » ne va pas sur une piste "
                f"{self.type.value} (attendus : {', '.join(acceptes)})")

    def ajouter(self, element: Element) -> None:
        """Pose un element, en refusant un chevauchement.

        Deux elements qui se recouvrent sur la MEME piste sont une
        ambiguite, pas une superposition : c'est l'ordre des pistes qui
        superpose. Les laisser passer produirait un rendu dependant de
        l'ordre d'insertion — donc imprevisible.
        """
        self._verifier_le_genre(element)
        for pose in self.elements:
            if element.debut_ms < pose.fin_ms and pose.debut_ms < element.fin_ms:
                raise ErreurProjet(
                    f"chevauchement sur la piste « {self.nom or self.identifiant} » : "
                    f"[{element.debut_ms}-{element.fin_ms}] ms recouvre "
                    f"[{pose.debut_ms}-{pose.fin_ms}] ms")
        self.elements.append(element)
        self.elements.sort(key=lambda e: e.debut_ms)

    @property
    def duree_ms(self) -> int:
        """La fin du dernier element. 0 pour une piste vide — ici, c'est une
        vraie mesure : une piste sans element dure bien zero."""
        return max((e.fin_ms for e in self.elements), default=0)


@dataclass
class Projet:
    """Un montage complet : ses medias, ses pistes, son format de sortie."""

    identifiant: str
    nom: str
    largeur: int = 1920
    hauteur: int = 1080
    images_par_seconde: int = 30
    medias: Dict[str, Media] = field(default_factory=dict)
    pistes: List[Piste] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.largeur <= 0 or self.hauteur <= 0:
            raise ErreurProjet(f"format invalide : {self.largeur}x{self.hauteur}")
        if self.images_par_seconde <= 0:
            raise ErreurProjet(f"cadence invalide : {self.images_par_seconde} im/s")

    # --- Lecture ------------------------------------------------------------------

    @property
    def duree_ms(self) -> int:
        """La duree du montage : la fin de son element le plus tardif."""
        return max((p.duree_ms for p in self.pistes), default=0)

    @property
    def format(self) -> str:
        """« 1920x1080 », tel qu'il partira au rendu."""
        return f"{self.largeur}x{self.hauteur}"

    def piste(self, identifiant: str) -> Piste:
        for piste in self.pistes:
            if piste.identifiant == identifiant:
                return piste
        raise ErreurProjet(f"aucune piste « {identifiant} » dans ce projet")

    def media(self, identifiant: str) -> Media:
        if identifiant not in self.medias:
            raise ErreurProjet(f"aucun media « {identifiant} » importe dans ce projet")
        return self.medias[identifiant]

    def elements(self) -> List[Element]:
        """Tous les elements, toutes pistes confondues, dans l'ordre du temps."""
        tous = [e for p in self.pistes for e in p.elements]
        return sorted(tous, key=lambda e: e.debut_ms)

    # --- Ecriture -----------------------------------------------------------------

    def ajouter_piste(self, type: TypePiste, nom: str = "") -> Piste:
        piste = Piste(identifiant=f"piste-{uuid.uuid4().hex[:8]}",
                      type=TypePiste(type), nom=nom)
        self.pistes.append(piste)
        return piste

    def ajouter_media(self, media: Media) -> Media:
        self.medias[media.identifiant] = media
        return media

    # --- Serialisation ------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Le projet en JSON pur : relisible par lui, reprenable par l'IA."""
        donnees = asdict(self)
        donnees["pistes"] = [
            {**asdict(p), "type": p.type.value} for p in self.pistes
        ]
        return donnees

    @classmethod
    def depuis_dict(cls, donnees: Dict[str, Any]) -> "Projet":
        """Reconstruit un projet, en revalidant tout au passage.

        Un projet relu d'un disque n'est pas plus digne de confiance qu'un
        projet recu d'ailleurs : il repasse par les memes controles.
        """
        medias = {i: Media(**m) for i, m in (donnees.get("medias") or {}).items()}
        pistes = []
        for brute in donnees.get("pistes") or []:
            elements = [Element(**e) for e in brute.get("elements") or []]
            pistes.append(Piste(
                identifiant=brute["identifiant"], type=TypePiste(brute["type"]),
                nom=brute.get("nom", ""), elements=elements,
                muette=brute.get("muette", False), masquee=brute.get("masquee", False)))
        return cls(
            identifiant=donnees["identifiant"], nom=donnees["nom"],
            largeur=donnees.get("largeur", 1920), hauteur=donnees.get("hauteur", 1080),
            images_par_seconde=donnees.get("images_par_seconde", 30),
            medias=medias, pistes=pistes)

    def ecrire(self, chemin: Path) -> Path:
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                          encoding="utf-8")
        return chemin

    @classmethod
    def lire(cls, chemin: Path) -> "Projet":
        return cls.depuis_dict(json.loads(Path(chemin).read_text(encoding="utf-8")))


def nouveau_projet(nom: str, largeur: int = 1920, hauteur: int = 1080,
                   images_par_seconde: int = 30) -> Projet:
    """Un projet vide, pret a recevoir des medias."""
    return Projet(identifiant=f"projet-{uuid.uuid4().hex[:8]}", nom=nom,
                  largeur=largeur, hauteur=hauteur,
                  images_par_seconde=images_par_seconde)
