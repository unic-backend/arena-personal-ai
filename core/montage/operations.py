"""Les operations de montage : ce que l'IA a le droit de faire a un projet.

C'est la couche que la mission OpenCut demande entre l'intelligence video et
le moteur : **le modele ne touche jamais l'etat interne directement.** Il
demande une operation nommee, avec des parametres ; l'operation valide, puis
execute, puis rend un compte-rendu.

Pourquoi cette frontiere plutot qu'un acces direct au `Projet` : un modele
qui se trompe de 3 secondes sur un `debut_ms` produit une timeline qui se
construit sans erreur et rend une video fausse. Ici, chaque operation dit ce
qu'elle a fait ou pourquoi elle a refuse — et un refus n'est jamais une
exception qui remonte au milieu d'une reponse.

**Trois regles :**

1. **Une operation rend un `Resultat`, elle ne leve pas.** L'appelant est un
   modele : il doit pouvoir lire l'echec et corriger, pas planter.

2. **Rien n'est mesure au jugé.** La duree d'un media vient de `ffprobe`,
   jamais d'une estimation. Un fichier illisible rend `duree_ms = None` et
   l'operation le dit — c'est la regle du projet : un champ absent n'est pas
   zero.

3. **Ce qui existe est reutilise.** `FFmpegTool` (`tools/video/ffmpeg_tool.py`)
   est deja la, teste, et trouve l'executable sur les deux plateformes du
   proprietaire. Aucun second chemin ffmpeg n'est cree ici.
"""
from __future__ import annotations

import json
import logging
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from core.montage.projet import (
    Element,
    ErreurProjet,
    Media,
    Projet,
    TypePiste,
    nouveau_projet,
)
from tools.video.ffmpeg_tool import FFmpegTool

logger = logging.getLogger("usman.montage.operations")

#: Ce que `ffprobe` met au maximum pour lire un fichier. Au-dela, le fichier
#: est considere illisible plutot que d'immobiliser une reponse.
DELAI_SONDE_SECONDES = 30

EXTENSIONS_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
EXTENSIONS_AUDIO = {".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac"}


@dataclass
class Resultat:
    """Ce qu'une operation rend : jamais une exception, toujours un etat lisible."""

    ok: bool
    operation: str
    message: str
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "operation": self.operation,
                "message": self.message, **self.detail}


def _ok(operation: str, message: str, **detail: Any) -> Resultat:
    return Resultat(True, operation, message, detail)


def _echec(operation: str, message: str, **detail: Any) -> Resultat:
    logger.info("Operation %s refusee : %s", operation, message)
    return Resultat(False, operation, message, detail)


def genre_du_fichier(chemin: str) -> Optional[str]:
    """« video », « image », « audio », ou None si l'extension est inconnue."""
    suffixe = Path(chemin).suffix.lower()
    if suffixe in EXTENSIONS_VIDEO:
        return "video"
    if suffixe in EXTENSIONS_IMAGE:
        return "image"
    if suffixe in EXTENSIONS_AUDIO:
        return "audio"
    return None


def sonder_le_media(chemin: str, ffmpeg: Optional[FFmpegTool] = None) -> Dict[str, Any]:
    """Duree et dimensions REELLES d'un fichier, par ffprobe.

    Rend un dictionnaire dont les champs valent `None` quand la mesure n'a
    pas eu lieu — jamais `0`, qui se lirait « fichier vide » alors que rien
    n'a ete lu.
    """
    inconnu: Dict[str, Any] = {"duree_ms": None, "largeur": None, "hauteur": None}
    outil = ffmpeg or FFmpegTool()
    if not outil.is_available():
        return inconnu

    # `ffprobe` est a cote de `ffmpeg` : meme dossier, meme installation.
    sonde = str(Path(outil.get_executable()).with_name(
        "ffprobe" + Path(outil.get_executable()).suffix))
    try:
        rendu = subprocess.run(
            [sonde, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", chemin],
            capture_output=True, text=True, timeout=DELAI_SONDE_SECONDES)
        if rendu.returncode != 0:
            return inconnu
        donnees = json.loads(rendu.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as erreur:
        logger.info("Media illisible par ffprobe (%s) : %s", type(erreur).__name__, chemin)
        return inconnu

    mesure = dict(inconnu)
    duree = (donnees.get("format") or {}).get("duration")
    if duree is not None:
        try:
            mesure["duree_ms"] = int(round(float(duree) * 1000))
        except (TypeError, ValueError):
            pass
    for flux in donnees.get("streams") or []:
        if flux.get("codec_type") == "video":
            mesure["largeur"] = flux.get("width")
            mesure["hauteur"] = flux.get("height")
            break
    return mesure


class Montage:
    """Les operations qu'un modele peut demander sur un projet.

    Une instance porte UN projet. Le modele ne le manipule jamais
    directement : il appelle des operations nommees.
    """

    def __init__(self, projet: Optional[Projet] = None,
                 ffmpeg: Optional[FFmpegTool] = None) -> None:
        self.projet = projet
        self.ffmpeg = ffmpeg or FFmpegTool()

    # --- Le projet ----------------------------------------------------------------

    def creer_projet(self, nom: str, largeur: int = 1920, hauteur: int = 1080,
                     images_par_seconde: int = 30) -> Resultat:
        try:
            self.projet = nouveau_projet(nom, largeur, hauteur, images_par_seconde)
        except ErreurProjet as erreur:
            return _echec("creer_projet", str(erreur))
        return _ok("creer_projet", f"Projet « {nom} » cree en {self.projet.format}.",
                   projet_id=self.projet.identifiant, format=self.projet.format)

    def _resoudre_piste(self, reference: str):
        """Une piste par son identifiant OU par son nom.

        Mesure du 01/09/2026, en jouant la chaine complete : un plan
        d'operations ecrit par un modele ne peut pas citer un identifiant
        genere PENDANT son execution — il ne le connait pas encore. Le nom
        que le plan a lui-meme donne a la piste est la seule reference qu'il
        puisse tenir d'un bout a l'autre.
        """
        for piste in self.projet.pistes:
            if piste.identifiant == reference or (piste.nom and piste.nom == reference):
                return piste
        raise ErreurProjet(
            f"aucune piste « {reference} » : donne son nom, ou cree-la d'abord")

    def _resoudre_media(self, reference: str) -> Media:
        """Un media par son identifiant, son nom d'alias, ou son nom de fichier."""
        if reference in self.projet.medias:
            return self.projet.medias[reference]
        for media in self.projet.medias.values():
            if reference in (media.nom, Path(media.chemin).name):
                return media
        raise ErreurProjet(f"aucun media « {reference} » importe dans ce projet")

    def _exige_un_projet(self, operation: str) -> Optional[Resultat]:
        if self.projet is None:
            return _echec(operation, "Aucun projet ouvert : cree-le d'abord.")
        return None

    # --- Les medias ---------------------------------------------------------------

    def importer_media(self, chemin: str, nom: str = "") -> Resultat:
        """Importe un fichier et MESURE sa duree. Jamais d'estimation."""
        refus = self._exige_un_projet("importer_media")
        if refus:
            return refus

        fichier = Path(chemin)
        if not fichier.is_file():
            return _echec("importer_media", f"Fichier introuvable : {chemin}")

        genre = genre_du_fichier(chemin)
        if genre is None:
            return _echec("importer_media",
                          f"Format non pris en charge : {fichier.suffix or 'aucune extension'}")

        mesure = sonder_le_media(chemin, self.ffmpeg)
        if genre in ("video", "audio") and mesure["duree_ms"] is None:
            return _echec(
                "importer_media",
                f"Duree illisible pour {fichier.name} : le fichier est peut-etre "
                "abime, ou ffmpeg n'est pas installe. Rien n'a ete importe.",
                duree_ms=None)

        media = Media(identifiant=f"media-{uuid.uuid4().hex[:8]}", chemin=str(fichier),
                      genre=genre, duree_ms=mesure["duree_ms"],
                      largeur=mesure["largeur"], hauteur=mesure["hauteur"],
                      nom=nom or fichier.name)
        self.projet.ajouter_media(media)
        return _ok("importer_media",
                   f"{fichier.name} importe ({genre}"
                   + (f", {media.duree_ms} ms" if media.duree_ms else "") + ").",
                   media_id=media.identifiant, nom=media.nom, genre=genre,
                   duree_ms=media.duree_ms,
                   largeur=media.largeur, hauteur=media.hauteur)

    # --- La timeline --------------------------------------------------------------

    def ajouter_piste(self, type: str, nom: str = "") -> Resultat:
        refus = self._exige_un_projet("ajouter_piste")
        if refus:
            return refus
        try:
            piste = self.projet.ajouter_piste(TypePiste(type), nom)
        except ValueError:
            attendus = ", ".join(t.value for t in TypePiste)
            return _echec("ajouter_piste",
                          f"Type de piste inconnu : {type!r}. Attendus : {attendus}.")
        return _ok("ajouter_piste", f"Piste {piste.type.value} ajoutee.",
                   piste_id=piste.identifiant, type=piste.type.value)

    def ajouter_clip(self, piste_id: str, media_id: str, debut_ms: int = 0,
                     duree_ms: Optional[int] = None,
                     coupe_debut_ms: int = 0) -> Resultat:
        """Pose un media sur une piste.

        Sans `duree_ms`, le clip prend toute la source restante — une valeur
        MESUREE a l'import, pas supposee.
        """
        refus = self._exige_un_projet("ajouter_clip")
        if refus:
            return refus
        try:
            media = self._resoudre_media(media_id)
            piste = self._resoudre_piste(piste_id)
        except ErreurProjet as erreur:
            return _echec("ajouter_clip", str(erreur))

        if duree_ms is None:
            if media.duree_ms is None:
                return _echec(
                    "ajouter_clip",
                    f"La duree de {Path(media.chemin).name} n'a pas ete mesuree "
                    "(image fixe ?) : donne une duree explicite.")
            duree_ms = media.duree_ms - coupe_debut_ms

        if media.duree_ms is not None and coupe_debut_ms + duree_ms > media.duree_ms:
            return _echec(
                "ajouter_clip",
                f"Le clip depasse la source : {coupe_debut_ms + duree_ms} ms "
                f"demandes sur {media.duree_ms} ms disponibles.")

        try:
            # L'identifiant RESOLU, jamais la reference du plan : un element
            # qui garderait « chantier » serait introuvable au rendu, qui ne
            # connait que les identifiants. Trouve en jouant la chaine
            # complete le 01/09/2026 — la composition passait, le rendu non.
            element = Element(identifiant=f"clip-{uuid.uuid4().hex[:8]}",
                              genre=media.genre, debut_ms=debut_ms, duree_ms=duree_ms,
                              media_id=media.identifiant, coupe_debut_ms=coupe_debut_ms)
            piste.ajouter(element)
        except ErreurProjet as erreur:
            return _echec("ajouter_clip", str(erreur))

        return _ok("ajouter_clip",
                   f"Clip pose a {debut_ms} ms pour {duree_ms} ms.",
                   element_id=element.identifiant, debut_ms=debut_ms, duree_ms=duree_ms)

    def ajouter_texte(self, piste_id: str, texte: str, debut_ms: int,
                      duree_ms: int, **proprietes: Any) -> Resultat:
        refus = self._exige_un_projet("ajouter_texte")
        if refus:
            return refus
        try:
            piste = self._resoudre_piste(piste_id)
            element = Element(identifiant=f"texte-{uuid.uuid4().hex[:8]}",
                              genre="texte", debut_ms=debut_ms, duree_ms=duree_ms,
                              contenu=texte, proprietes=dict(proprietes))
            piste.ajouter(element)
        except ErreurProjet as erreur:
            return _echec("ajouter_texte", str(erreur))
        return _ok("ajouter_texte", f"Texte « {texte[:40]} » pose a {debut_ms} ms.",
                   element_id=element.identifiant)

    def couper_clip(self, piste_id: str, element_id: str, instant_ms: int) -> Resultat:
        """Coupe un clip en deux a un instant de la TIMELINE."""
        refus = self._exige_un_projet("couper_clip")
        if refus:
            return refus
        try:
            piste = self._resoudre_piste(piste_id)
        except ErreurProjet as erreur:
            return _echec("couper_clip", str(erreur))

        cible = next((e for e in piste.elements if e.identifiant == element_id), None)
        if cible is None:
            return _echec("couper_clip", f"Aucun element « {element_id} » sur cette piste.")
        if not (cible.debut_ms < instant_ms < cible.fin_ms):
            return _echec(
                "couper_clip",
                f"L'instant {instant_ms} ms tombe hors du clip "
                f"[{cible.debut_ms}-{cible.fin_ms}] ms : rien a couper.")

        avant_duree = instant_ms - cible.debut_ms
        apres = Element(
            identifiant=f"clip-{uuid.uuid4().hex[:8]}", genre=cible.genre,
            debut_ms=instant_ms, duree_ms=cible.fin_ms - instant_ms,
            media_id=cible.media_id, coupe_debut_ms=cible.coupe_debut_ms + avant_duree,
            contenu=cible.contenu, proprietes=dict(cible.proprietes))
        cible.duree_ms = avant_duree
        piste.elements.append(apres)
        piste.elements.sort(key=lambda e: e.debut_ms)
        return _ok("couper_clip", f"Clip coupe a {instant_ms} ms.",
                   avant=cible.identifiant, apres=apres.identifiant)

    def retirer_element(self, piste_id: str, element_id: str) -> Resultat:
        refus = self._exige_un_projet("retirer_element")
        if refus:
            return refus
        try:
            piste = self._resoudre_piste(piste_id)
        except ErreurProjet as erreur:
            return _echec("retirer_element", str(erreur))
        avant = len(piste.elements)
        piste.elements = [e for e in piste.elements if e.identifiant != element_id]
        if len(piste.elements) == avant:
            return _echec("retirer_element", f"Aucun element « {element_id} » a retirer.")
        return _ok("retirer_element", "Element retire.")

    def definir_format(self, largeur: int, hauteur: int) -> Resultat:
        """Change le format de sortie — 9:16 pour un Reel, 16:9 pour YouTube."""
        refus = self._exige_un_projet("definir_format")
        if refus:
            return refus
        if largeur <= 0 or hauteur <= 0:
            return _echec("definir_format", f"Format invalide : {largeur}x{hauteur}")
        self.projet.largeur, self.projet.hauteur = largeur, hauteur
        return _ok("definir_format", f"Format de sortie : {self.projet.format}.",
                   format=self.projet.format)

    # --- Lecture ------------------------------------------------------------------

    def resumer(self) -> Resultat:
        """L'etat du projet, tel qu'un humain ou un modele peut le relire."""
        refus = self._exige_un_projet("resumer")
        if refus:
            return refus
        pistes = [{"id": p.identifiant, "type": p.type.value, "nom": p.nom,
                   "elements": len(p.elements), "duree_ms": p.duree_ms}
                  for p in self.projet.pistes]
        return _ok("resumer",
                   f"« {self.projet.nom} » : {len(pistes)} piste(s), "
                   f"{self.projet.duree_ms} ms, {self.projet.format}.",
                   projet_id=self.projet.identifiant, duree_ms=self.projet.duree_ms,
                   format=self.projet.format, pistes=pistes,
                   medias=len(self.projet.medias))
