"""Le rendu : de la timeline au fichier video, et la preuve que le fichier tient.

Ce module est le seul endroit qui exécute. `projet.py` decrit, `operations.py`
valide, `rendu.py` produit — et **verifie ce qu'il a produit**.

La regle qui gouverne tout le fichier vient de la mission et du projet :
« Ne pas rapporter un succes parce qu'une commande de rendu a ete lancee. »
Un `returncode == 0` de ffmpeg ne prouve rien : le fichier peut etre absent,
vide, ou durer 0,2 s au lieu de 30 s. `rendre()` re-sonde donc sa propre
sortie avec ffprobe et compare a ce que le projet annonçait.

**Pourquoi ffmpeg et pas le moteur d'OpenCut** (`docs/audits/opencut_audit.md`) :
le rendu d'OpenCut classic est natif navigateur (WebCodecs + canvas), sans
chemin headless, et son depot est archive. ffmpeg est deja la, local,
compatible avec la RTX A2000 du proprietaire, et deja utilise par le reste
d'ARENA. La frontiere est ici : `rendre(projet, sortie)` ne dit rien de
ffmpeg dans sa signature, donc un autre moteur — la reecriture d'OpenCut le
jour ou elle livre son Editor API — se branche sans toucher au reste.

**Ce qui est rendu, et ce qui ne l'est pas.** Les pistes VIDEO, IMAGE, TEXTE
et AUDIO sont composees. Les transitions, masques et effets d'OpenCut ne le
sont pas : ARENA n'a pas de moteur pour eux, et une transition declaree mais
non rendue serait une capacite annoncee absente.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.montage.operations import sonder_le_media
from core.montage.projet import Element, Projet, TypePiste

logger = logging.getLogger("usman.montage.rendu")

#: Au-dela, le rendu est interrompu et le dit. Un montage long sur processeur
#: peut etre lent ; ce plafond protege la reponse, pas la qualite.
DELAI_RENDU_SECONDES = 900

#: Tolerance entre la duree annoncee par le projet et celle du fichier rendu.
#: ffmpeg arrondit a l'image pres ; a 30 im/s, une image vaut 33 ms.
TOLERANCE_DUREE_MS = 400


@dataclass
class Rendu:
    """Le compte-rendu d'un rendu, avec ce qui a ete VERIFIE sur le fichier."""

    ok: bool
    message: str
    chemin: Optional[str] = None
    octets: Optional[int] = None
    duree_ms: Optional[int] = None
    largeur: Optional[int] = None
    hauteur: Optional[int] = None
    duree_attendue_ms: Optional[int] = None
    commande: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "message": self.message, "chemin": self.chemin,
                "octets": self.octets, "duree_ms": self.duree_ms,
                "largeur": self.largeur, "hauteur": self.hauteur,
                "duree_attendue_ms": self.duree_attendue_ms}


def _texte_pour_ffmpeg(texte: str) -> str:
    """Echappe ce qui casserait un filtre `drawtext`.

    Sans ça, une apostrophe dans « l'Almadies » ferme la chaine du filtre et
    ffmpeg refuse tout le rendu — pour un nom de chantier parfaitement legitime.
    """
    for avant, apres in (("\\", "\\\\"), (":", "\\:"), ("'", "’"),
                         ("%", "\\%"), ("[", "\\["), ("]", "\\]"), (",", "\\,")):
        texte = texte.replace(avant, apres)
    return texte


#: Les couleurs qu'un appelant peut nommer : un mot, un `#rrggbb`, un
#: `0xrrggbb`, chacun avec une opacite `@0.5` optionnelle. Rien d'autre.
_COULEUR = re.compile(r"^(?:[A-Za-z]{1,20}|#[0-9A-Fa-f]{6,8}|0x[0-9A-Fa-f]{6,8})"
                      r"(?:@(?:0|1|0?\.\d{1,3}))?$")

#: Les expressions de position que ffmpeg accepte, reduites a ce qui sert :
#: des nombres, les variables de drawtext, et l'arithmetique. Pas de `:`,
#: pas de `,`, pas de guillemet — donc aucun moyen d'ouvrir une autre option.
_EXPRESSION = re.compile(r"^[0-9A-Za-z_+\-*/(). ]{1,80}$")


def _propriete_sure(valeur: Any, motif: "re.Pattern[str]", defaut: Any) -> Any:
    """La valeur si elle tient dans le motif, le defaut sinon.

    **Sans ce filtre, les proprietes libres etaient interpolees telles quelles
    dans `filter_complex`.** Un `couleur` valant `white:fontfile=/etc/passwd`
    ouvrait une option ffmpeg supplementaire — et `drawtext` sait lire un
    fichier (`textfile=`), donc le contenu d'un fichier de la machine pouvait
    finir INCRUSTE dans une video que le proprietaire publie. Mesure du
    01/09/2026, sur du code ecrit la veille : la barriere de
    `core/montage/planificateur.py` couvrait `importer_media` et laissait
    passer les proprietes de `ajouter_texte`.

    Le contenu du texte, lui, etait deja echappe (`_texte_pour_ffmpeg`).
    """
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, str) and motif.match(valeur):
        return valeur
    if valeur is not None:
        logger.warning("Propriete refusee (hors motif) : %r — defaut applique.", valeur)
    return defaut


def _entier_sur(valeur: Any, defaut: int, minimum: int = 1, maximum: int = 4000) -> int:
    """Un entier dans des bornes, ou le defaut. Jamais une chaine libre."""
    try:
        entier = int(valeur)
    except (TypeError, ValueError):
        return defaut
    return entier if minimum <= entier <= maximum else defaut


class CompilateurFiltres:
    """Traduit une timeline en un graphe de filtres ffmpeg.

    Sorti dans sa propre classe pour être **testable sans rendre** : la
    construction du graphe se verifie en lisant la commande, sans attendre
    qu'un encodage se termine.
    """

    def __init__(self, projet: Projet) -> None:
        self.projet = projet

    def entrees(self) -> List[str]:
        """Les `-i` de la commande, dans l'ordre ou les filtres les citent."""
        arguments: List[str] = []
        # Un fond noir de la duree du projet : c'est sur lui que tout se pose.
        # Sans lui, un trou entre deux clips ferait echouer la concatenation.
        arguments += ["-f", "lavfi", "-i",
                      f"color=c=black:s={self.projet.largeur}x{self.projet.hauteur}"
                      f":r={self.projet.images_par_seconde}"
                      f":d={max(self.projet.duree_ms, 1) / 1000:.3f}"]
        for media in self._medias_utilises():
            arguments += ["-i", media.chemin]
        return arguments

    def _medias_utilises(self) -> List[Any]:
        """Les medias reellement poses sur une piste, dans un ordre stable."""
        vus: List[str] = []
        for piste in self.projet.pistes:
            for element in piste.elements:
                if element.media_id and element.media_id not in vus:
                    vus.append(element.media_id)
        return [self.projet.media(i) for i in vus]

    def _index_entree(self, media_id: str) -> int:
        """Le numero d'entree ffmpeg d'un media (0 = le fond noir)."""
        for numero, media in enumerate(self._medias_utilises(), start=1):
            if media.identifiant == media_id:
                return numero
        raise KeyError(media_id)

    def _filtre_visuel(self, element: Element, source: str, cible: str) -> List[str]:
        """Pose un element visuel sur le flux `source`, rend `cible`."""
        debut, fin = element.debut_ms / 1000, element.fin_ms / 1000
        etapes: List[str] = []

        if element.genre == "texte":
            props = element.proprietes
            etapes.append(
                f"[{source}]drawtext=text='{_texte_pour_ffmpeg(element.contenu)}'"
                f":fontsize={_entier_sur(props.get('taille'), 48, 8, 400)}"
                f":fontcolor={_propriete_sure(props.get('couleur'), _COULEUR, 'white')}"
                f":x={_propriete_sure(props.get('x'), _EXPRESSION, '(w-text_w)/2')}"
                f":y={_propriete_sure(props.get('y'), _EXPRESSION, 'h-th-80')}"
                f":box=1:boxcolor=black@0.5:boxborderw=12"
                f":enable='between(t,{debut:.3f},{fin:.3f})'[{cible}]")
            return etapes

        entree = self._index_entree(element.media_id)
        prepare = f"prep_{element.identifiant}"
        if element.genre == "video":
            coupe = element.coupe_debut_ms / 1000
            etapes.append(
                f"[{entree}:v]trim=start={coupe:.3f}:duration={element.duree_ms / 1000:.3f},"
                f"setpts=PTS-STARTPTS+{debut:.3f}/TB,"
                f"scale={self.projet.largeur}:{self.projet.hauteur}"
                f":force_original_aspect_ratio=decrease,"
                f"pad={self.projet.largeur}:{self.projet.hauteur}"
                f":(ow-iw)/2:(oh-ih)/2[{prepare}]")
            etapes.append(
                f"[{source}][{prepare}]overlay=0:0"
                f":enable='between(t,{debut:.3f},{fin:.3f})'[{cible}]")
        else:  # image — un logo, une photo de chantier
            props = element.proprietes
            largeur = _entier_sur(props.get("largeur"),
                                  int(self.projet.largeur * 0.25), 1, 8000)
            etapes.append(f"[{entree}:v]scale={largeur}:-1[{prepare}]")
            etapes.append(
                f"[{source}][{prepare}]"
                f"overlay={_propriete_sure(props.get('x'), _EXPRESSION, 40)}"
                f":{_propriete_sure(props.get('y'), _EXPRESSION, 40)}"
                f":enable='between(t,{debut:.3f},{fin:.3f})'[{cible}]")
        return etapes

    def graphe(self) -> tuple:
        """Rend `(filtre_complexe, etiquette_video, etiquette_audio_ou_None)`."""
        etapes: List[str] = []
        courant = "0:v"
        compteur = 0

        # L'ordre des pistes est l'ordre de superposition : la video en bas,
        # les images puis les textes par-dessus. C'est le meme ordre que
        # celui d'un editeur, et il est explicite plutot que subi.
        ordre = {TypePiste.VIDEO: 0, TypePiste.IMAGE: 1, TypePiste.TEXTE: 2}
        visuelles = sorted(
            (p for p in self.projet.pistes
             if p.type in ordre and not p.masquee and p.elements),
            key=lambda p: ordre[p.type])

        for piste in visuelles:
            for element in piste.elements:
                compteur += 1
                cible = f"v{compteur}"
                etapes += self._filtre_visuel(element, courant, cible)
                courant = cible

        etiquette_audio = None
        pistes_audio = [p for p in self.projet.pistes
                        if p.type == TypePiste.AUDIO and not p.muette and p.elements]
        flux_audio: List[str] = []
        for piste in pistes_audio:
            for element in piste.elements:
                compteur += 1
                sortie = f"a{compteur}"
                entree = self._index_entree(element.media_id)
                coupe = element.coupe_debut_ms / 1000
                etapes.append(
                    f"[{entree}:a]atrim=start={coupe:.3f}"
                    f":duration={element.duree_ms / 1000:.3f},"
                    f"asetpts=PTS-STARTPTS,"
                    f"adelay={element.debut_ms}|{element.debut_ms}[{sortie}]")
                flux_audio.append(f"[{sortie}]")
        if flux_audio:
            etiquette_audio = "aout"
            etapes.append(f"{''.join(flux_audio)}amix=inputs={len(flux_audio)}"
                          f":dropout_transition=0[{etiquette_audio}]")

        return ";".join(etapes), courant, etiquette_audio

    def commande(self, sortie: Path, ffmpeg: str) -> List[str]:
        """La commande ffmpeg complete, prete a lancer."""
        filtre, video, audio = self.graphe()
        commande = [ffmpeg, "-v", "error", "-y"] + self.entrees()
        if filtre:
            commande += ["-filter_complex", filtre, "-map", f"[{video}]"]
        else:
            commande += ["-map", "0:v"]
        if audio:
            commande += ["-map", f"[{audio}]", "-c:a", "aac"]
        commande += ["-t", f"{self.projet.duree_ms / 1000:.3f}",
                     "-r", str(self.projet.images_par_seconde),
                     "-c:v", "libx264", "-preset", "veryfast",
                     "-pix_fmt", "yuv420p", str(sortie)]
        return commande


def rendre(projet: Projet, sortie: Path,
           ffmpeg: Optional[str] = None) -> Rendu:
    """Rend le projet en un fichier video, puis VERIFIE ce fichier.

    Un rendu n'est un succes que si le fichier existe, n'est pas vide, se
    relit, et dure ce que le projet annonçait. Un `returncode == 0` seul ne
    suffit pas — c'est exactement ce que la mission interdit d'appeler un
    succes.
    """
    sortie = Path(sortie)
    if projet.duree_ms <= 0:
        return Rendu(False, "Le projet est vide : il n'y a rien a rendre.")

    binaire = ffmpeg or shutil.which("ffmpeg")
    if not binaire:
        return Rendu(False, "ffmpeg est introuvable : aucun rendu possible. "
                            "Installe-le, puis relance.")

    commande = CompilateurFiltres(projet).commande(sortie, binaire)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    try:
        rendu = subprocess.run(commande, capture_output=True, text=True,
                               timeout=DELAI_RENDU_SECONDES)
    except subprocess.TimeoutExpired:
        sortie.unlink(missing_ok=True)
        return Rendu(False, f"Rendu interrompu apres {DELAI_RENDU_SECONDES} s.",
                     commande=commande)
    except OSError as erreur:
        return Rendu(False, f"ffmpeg n'a pas pu demarrer : {erreur}", commande=commande)

    if rendu.returncode != 0:
        sortie.unlink(missing_ok=True)
        detail = (rendu.stderr or "").strip().splitlines()
        return Rendu(False, "ffmpeg a refuse le montage : "
                            + (detail[-1] if detail else "sans message"),
                     commande=commande)

    # --- La verification, qui est le vrai travail de cette fonction -------------
    if not sortie.exists():
        return Rendu(False, "ffmpeg s'est termine sans laisser de fichier.",
                     commande=commande)
    octets = sortie.stat().st_size
    if octets == 0:
        sortie.unlink(missing_ok=True)
        return Rendu(False, "Le fichier rendu est vide.", commande=commande)

    mesure = sonder_le_media(str(sortie))
    if mesure["duree_ms"] is None:
        return Rendu(False, "Le fichier rendu ne se relit pas : conteneur invalide.",
                     chemin=str(sortie), octets=octets, commande=commande)

    ecart = abs(mesure["duree_ms"] - projet.duree_ms)
    if ecart > TOLERANCE_DUREE_MS:
        return Rendu(False,
                     f"Duree rendue incoherente : {mesure['duree_ms']} ms au lieu "
                     f"de {projet.duree_ms} ms attendues.",
                     chemin=str(sortie), octets=octets, duree_ms=mesure["duree_ms"],
                     duree_attendue_ms=projet.duree_ms, commande=commande)

    return Rendu(True,
                 f"Video rendue : {mesure['duree_ms']} ms, "
                 f"{mesure['largeur']}x{mesure['hauteur']}, {octets} octets.",
                 chemin=str(sortie), octets=octets, duree_ms=mesure["duree_ms"],
                 largeur=mesure["largeur"], hauteur=mesure["hauteur"],
                 duree_attendue_ms=projet.duree_ms, commande=commande)
