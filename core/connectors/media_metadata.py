"""`media_metadata` : ce qu'un fichier dit vraiment de lui-meme, jamais plus.

**Audit avant d'ecrire une ligne** (mission EXIF & Media Metadata) : ARENA
n'avait AUCUNE capacite qui rend les metadonnees techniques d'un media —
`core/montage/operations.py::sonder_le_media` mesure duree/largeur/hauteur
par ffprobe, mais uniquement pour l'import dans un projet de montage, jamais
expose comme une reponse a « quelles sont les infos EXIF de cette photo ? ».
Aucun EXIF (date, appareil, GPS, ISO, ouverture...) n'etait lu nulle part.
Rien de tout cela n'est duplique ici : ce connecteur est le seul point qui
rend des metadonnees techniques, et il reutilise ce qui existe deja —
Pillow (deja une dependance, `core/production/conversion/moteurs.py`) pour
les images, `FFmpegTool` (deja une dependance, `tools/video/ffmpeg_tool.py`)
pour video/audio, et `genre_du_fichier` (`core/montage/operations.py`) pour
classer un fichier par extension, plutot que d'en ecrire une quatrieme copie
(audio_voix.py et audio_agent.py en ont deja chacun la leur, pour leurs
propres besoins etroits).

**Etudie, jamais copie** : `ternera/exif-viewer` (extension de navigateur,
lit l'EXIF d'une image ouverte dans l'onglet actif via `exif-js` cote
client). Aucune ligne de ce depot n'entre ici — c'est une interface, pas un
moteur, et ARENA n'a besoin d'aucune extension de navigateur. Ce qui est
repris : la LISTE des champs EXIF qu'un lecteur serieux doit couvrir
(fabricant, modele, objectif, ISO, ouverture, vitesse, focale, GPS, date,
logiciel, copyright, orientation) — une checklist, pas du code. Detail
complet -> `docs/audits/exif_viewer_audit.md`.

**Quatre regles, au-dela du contrat commun `Connecteur`** :

1. **Rien n'est invente.** Un champ EXIF absent reste `None` — jamais une
   valeur plausible. Pillow et ffprobe sont interroges, jamais supposes.
2. **Le GPS ne sort jamais de cette reponse.** Les coordonnees lues restent
   dans le `detail` du resultat, jamais journalisees a part, jamais
   envoyees a un service externe (aucun appel reseau dans ce fichier), et
   ne sont ecrites en memoire longue duree que si l'appelant le fait
   lui-meme, explicitement — ce connecteur ne persiste rien.
3. **`format_reel` n'est PAS l'extension.** Un fichier `.jpg` qui est en
   realite un PNG (ou l'inverse) est signale : le format vient de ce que
   Pillow/ffprobe ont reellement lu dans les octets, jamais du nom du
   fichier.
4. **Une lecture est une lecture.** Aucune capacite de ce connecteur
   n'ecrit rien : `ecriture=False` partout, aucune confirmation requise —
   contrairement a une conversion ou un rendu.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.montage.operations import EXTENSIONS_IMAGE, genre_du_fichier
from tools.video.ffmpeg_tool import FFmpegTool

logger = logging.getLogger("usman.connecteurs.media_metadata")

#: Meme plafond que `core/montage/operations.py::DELAI_SONDE_SECONDES` — un
#: fichier illisible ne doit pas immobiliser une reponse.
DELAI_SONDE_SECONDES = 30

#: Formats d'image que Pillow sait ouvrir ET dont ce module lit l'EXIF.
#: Superset volontaire de `EXTENSIONS_IMAGE` (montage) : WebP et TIFF sont
#: des formats d'image que Pillow ouvre tres bien pour LIRE des metadonnees,
#: meme si le montage video ne les monte jamais sur une piste.
EXTENSIONS_IMAGE_METADATA = EXTENSIONS_IMAGE | {".tif", ".tiff"}


def _dms_vers_decimal(dms, ref: Optional[str]) -> Optional[float]:
    """`((deg),(min),(sec))`, `ref` ('N'/'S'/'E'/'W') -> degres decimaux signes.

    `None` si l'un des deux manque : une coordonnee GPS incomplete n'est
    jamais devinee a moitie.
    """
    if not dms or not ref:
        return None
    try:
        degres, minutes, secondes = (float(v) for v in dms)
    except (TypeError, ValueError):
        return None
    valeur = degres + minutes / 60.0 + secondes / 3600.0
    if ref.upper() in ("S", "W"):
        valeur = -valeur
    return round(valeur, 6)


def _vitesse_lisible(exposition) -> Optional[str]:
    """`0.004` -> `"1/250s"`. Une vitesse >= 1s s'affiche en secondes."""
    try:
        secondes = float(exposition)
    except (TypeError, ValueError):
        return None
    if secondes <= 0:
        return None
    if secondes >= 1:
        return f"{secondes:.1f}s"
    denominateur = round(1 / secondes)
    return f"1/{denominateur}s"


def _metadata_image(source: Any) -> Dict[str, Any]:
    """Ce que Pillow lit vraiment sur une image. Jamais un champ suppose.

    `source` : un `Path` (fichier sur disque) ou un flux en memoire
    (`io.BytesIO`, utilise par `ConnecteurMediaMetadata._analyser_image_en_memoire`
    pour une piece jointe jamais ecrite sur disque) — `PIL.Image.open` accepte
    les deux de la meme facon.
    """
    resultat: Dict[str, Any] = {
        "genre": "image", "format_reel": None, "largeur": None, "hauteur": None,
        "mode_couleur": None, "orientation": None, "date_prise": None,
        "fabricant": None, "modele_appareil": None, "objectif": None,
        "iso": None, "ouverture": None, "vitesse_obturation": None,
        "focale_mm": None, "logiciel": None, "copyright": None,
        "gps_present": False, "gps_latitude": None, "gps_longitude": None,
        "lisible": False,
    }
    try:
        from PIL import Image
        from PIL.ExifTags import GPS as Gps
        from PIL.ExifTags import Base as Tag

        with Image.open(source) as img:
            resultat["format_reel"] = img.format
            resultat["largeur"], resultat["hauteur"] = img.size
            resultat["mode_couleur"] = img.mode
            resultat["lisible"] = True

            exif = img.getexif()
            if not exif:
                return resultat

            resultat["orientation"] = exif.get(Tag.Orientation.value)
            resultat["date_prise"] = (
                exif.get(Tag.DateTimeOriginal.value) or exif.get(Tag.DateTime.value))
            resultat["fabricant"] = exif.get(Tag.Make.value)
            resultat["modele_appareil"] = exif.get(Tag.Model.value)
            resultat["logiciel"] = exif.get(Tag.Software.value)
            resultat["copyright"] = exif.get(Tag.Copyright.value)

            try:
                sous_ifd = exif.get_ifd(Tag.ExifOffset.value)
            except Exception:  # noqa: BLE001 — un sous-IFD corrompu n'est pas l'image entiere
                sous_ifd = {}
            if sous_ifd:
                resultat["objectif"] = sous_ifd.get(Tag.LensModel.value)
                iso = sous_ifd.get(Tag.ISOSpeedRatings.value)
                resultat["iso"] = int(iso) if iso is not None else None
                fnombre = sous_ifd.get(Tag.FNumber.value)
                resultat["ouverture"] = f"f/{float(fnombre):.1f}" if fnombre is not None else None
                resultat["vitesse_obturation"] = _vitesse_lisible(
                    sous_ifd.get(Tag.ExposureTime.value))
                focale = sous_ifd.get(Tag.FocalLength.value)
                resultat["focale_mm"] = float(focale) if focale is not None else None

            try:
                gps_ifd = exif.get_ifd(Tag.GPSInfo.value)
            except Exception:  # noqa: BLE001
                gps_ifd = {}
            if gps_ifd:
                lat = _dms_vers_decimal(
                    gps_ifd.get(Gps.GPSLatitude.value), gps_ifd.get(Gps.GPSLatitudeRef.value))
                lon = _dms_vers_decimal(
                    gps_ifd.get(Gps.GPSLongitude.value), gps_ifd.get(Gps.GPSLongitudeRef.value))
                if lat is not None and lon is not None:
                    resultat["gps_present"] = True
                    resultat["gps_latitude"] = lat
                    resultat["gps_longitude"] = lon
    except Exception as erreur:  # noqa: BLE001 — une image illisible est un etat, pas un crash
        logger.info("Image illisible (%s) : %s", type(erreur).__name__, source)
        resultat["erreur"] = f"{type(erreur).__name__} : {erreur}"
    return resultat


def _ffprobe_json(chemin: Path, ffmpeg: FFmpegTool) -> Optional[Dict[str, Any]]:
    """La sortie JSON complete de ffprobe, ou `None` si illisible.

    Meme decouverte d'executable que `core/montage/operations.py::
    sonder_le_media` (ffprobe a cote de ffmpeg) — mais cette fonction
    demande TOUT (`-show_format -show_streams`) plutot que les trois champs
    dont le montage a besoin, parce que la video/audio de ce connecteur veut
    codec, fps, bitrate, pistes audio et tags, que ce probe etroit ne rend
    pas.
    """
    if not ffmpeg.is_available():
        return None
    sonde = str(Path(ffmpeg.get_executable()).with_name(
        "ffprobe" + Path(ffmpeg.get_executable()).suffix))
    try:
        rendu = subprocess.run(
            [sonde, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(chemin)],
            capture_output=True, text=True, timeout=DELAI_SONDE_SECONDES)
        if rendu.returncode != 0:
            return None
        return json.loads(rendu.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as erreur:
        logger.info("ffprobe illisible (%s) : %s", type(erreur).__name__, chemin)
        return None


def _metadata_video(chemin: Path, ffmpeg: FFmpegTool) -> Dict[str, Any]:
    resultat: Dict[str, Any] = {
        "genre": "video", "conteneur": None, "codec_video": None,
        "largeur": None, "hauteur": None, "fps": None, "duree_ms": None,
        "bitrate_kbps": None, "pistes_audio": [], "tags": {}, "lisible": False,
    }
    donnees = _ffprobe_json(chemin, ffmpeg)
    if donnees is None:
        resultat["erreur"] = "ffprobe indisponible ou fichier illisible"
        return resultat

    fmt = donnees.get("format") or {}
    resultat["lisible"] = True
    resultat["conteneur"] = fmt.get("format_name")
    resultat["tags"] = fmt.get("tags") or {}
    duree = fmt.get("duration")
    if duree is not None:
        try:
            resultat["duree_ms"] = int(round(float(duree) * 1000))
        except (TypeError, ValueError):
            pass
    bitrate = fmt.get("bit_rate")
    if bitrate is not None:
        try:
            resultat["bitrate_kbps"] = round(int(bitrate) / 1000)
        except (TypeError, ValueError):
            pass

    pistes_audio: List[Dict[str, Any]] = []
    for flux in donnees.get("streams") or []:
        if flux.get("codec_type") == "video" and resultat["codec_video"] is None:
            resultat["codec_video"] = flux.get("codec_name")
            resultat["largeur"] = flux.get("width")
            resultat["hauteur"] = flux.get("height")
            taux = flux.get("r_frame_rate") or flux.get("avg_frame_rate")
            resultat["fps"] = _taux_vers_float(taux)
        elif flux.get("codec_type") == "audio":
            pistes_audio.append({
                "codec": flux.get("codec_name"),
                "canaux": flux.get("channels"),
                "echantillonnage_hz": _vers_int(flux.get("sample_rate")),
                "langue": (flux.get("tags") or {}).get("language"),
            })
    resultat["pistes_audio"] = pistes_audio
    return resultat


def _metadata_audio(chemin: Path, ffmpeg: FFmpegTool) -> Dict[str, Any]:
    resultat: Dict[str, Any] = {
        "genre": "audio", "conteneur": None, "codec": None, "duree_ms": None,
        "bitrate_kbps": None, "echantillonnage_hz": None, "canaux": None,
        "tags": {}, "lisible": False,
    }
    donnees = _ffprobe_json(chemin, ffmpeg)
    if donnees is None:
        resultat["erreur"] = "ffprobe indisponible ou fichier illisible"
        return resultat

    fmt = donnees.get("format") or {}
    resultat["lisible"] = True
    resultat["conteneur"] = fmt.get("format_name")
    resultat["tags"] = fmt.get("tags") or {}
    duree = fmt.get("duration")
    if duree is not None:
        try:
            resultat["duree_ms"] = int(round(float(duree) * 1000))
        except (TypeError, ValueError):
            pass
    bitrate = fmt.get("bit_rate")
    if bitrate is not None:
        try:
            resultat["bitrate_kbps"] = round(int(bitrate) / 1000)
        except (TypeError, ValueError):
            pass

    for flux in donnees.get("streams") or []:
        if flux.get("codec_type") == "audio":
            resultat["codec"] = flux.get("codec_name")
            resultat["echantillonnage_hz"] = _vers_int(flux.get("sample_rate"))
            resultat["canaux"] = flux.get("channels")
            break
    return resultat


def _taux_vers_float(taux: Optional[str]) -> Optional[float]:
    """`"30000/1001"` -> `29.97`. `None` si absent ou mal forme."""
    if not taux:
        return None
    try:
        if "/" in taux:
            num, den = taux.split("/", 1)
            den_f = float(den)
            return round(float(num) / den_f, 3) if den_f else None
        return round(float(taux), 3)
    except (TypeError, ValueError):
        return None


def _vers_int(valeur) -> Optional[int]:
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


class ConnecteurMediaMetadata(Connecteur):
    """`media_metadata` : lit, jamais n'ecrit, jamais n'invente."""

    service = "media_metadata"
    nom = "media_metadata"

    def __init__(self, ffmpeg: Optional[FFmpegTool] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.ffmpeg = ffmpeg or FFmpegTool()

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "analyser": Capacite(
                nom="analyser", action="read",
                description=(
                    "Lit les metadonnees techniques reelles d'une image, d'une "
                    "video ou d'un fichier audio deja sur la machine — jamais "
                    "une capacite qui ecrit ou modifie le fichier."),
                ecriture=False),
        }

    def sonder(self) -> Sante:
        """Aucun service externe : `Connecteur.sonder()` par defaut reste
        `OPERATIONNEL` tant que Pillow est importable — verifie ici pour de
        vrai, pas suppose."""
        from core.connectors.base import _maintenant

        try:
            import PIL  # noqa: F401
        except ImportError as erreur:
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message=f"Pillow n'est pas installe : {erreur}",
                         ce_qui_manque="Pillow (deja dans requirements.txt)",
                         mesure_le=_maintenant())
        return Sante(etat=EtatSante.OPERATIONNEL,
                     message="Pillow disponible pour les images ; "
                             f"ffmpeg/ffprobe {'disponible' if self.ffmpeg.is_available() else 'absent'} "
                             "pour video/audio.",
                     mesure_le=_maintenant())

    def authentifier(self) -> bool:
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        return self._analyser(**parametres)

    def _analyser(self, chemin: str = "", image_base64: str = "",
                  nom_fichier: str = "", **_: Any) -> ResultatAction:
        if not chemin and image_base64:
            # Chemin d'entree utilise par `agents/vision/vision_agent.py` :
            # une piece jointe (`PieceJointe`) ne vit qu'en base64, jamais
            # ecrite sur disque (`apps/backend/pieces_jointes.py`). Pillow
            # ouvre un flux en memoire exactement comme un fichier — aucune
            # ecriture temporaire necessaire.
            return self._analyser_image_en_memoire(image_base64, nom_fichier)

        source = Path(chemin) if chemin else None
        if source is None or not source.is_file():
            return echec(action="analyser", cible=self.nom,
                         message=f"Fichier introuvable : « {chemin or '(aucun)'} ».")

        genre = genre_du_fichier(str(source))
        if genre is None:
            # L'extension ne dit rien — mais peut-etre que le contenu, si.
            # Une extension absente/inconnue n'est pas une raison de refuser
            # avant meme d'avoir regarde : Pillow sait ouvrir un fichier
            # sans extension correcte, ffprobe aussi.
            genre = "image" if source.suffix.lower() in EXTENSIONS_IMAGE_METADATA else None

        if genre == "image" or source.suffix.lower() in EXTENSIONS_IMAGE_METADATA:
            detail = _metadata_image(source)
        elif genre == "video":
            detail = _metadata_video(source, self.ffmpeg)
        elif genre == "audio":
            detail = _metadata_audio(source, self.ffmpeg)
        else:
            return echec(
                action="analyser", cible=self.nom,
                message=(f"Extension « {source.suffix or '(aucune)'} » non reconnue "
                         "comme image, video ou audio : rien a analyser."))

        if not detail.get("lisible"):
            return echec(
                action="analyser", cible=self.nom,
                message=(f"« {source.name} » n'a pas pu etre lu comme "
                         f"{detail.get('genre', 'media')} : "
                         f"{detail.get('erreur', 'raison inconnue')}."),
                **detail)

        # Un fichier dont l'extension prometait autre chose que ce que le
        # contenu contient reellement : signale, jamais tu (regle 3).
        extension = source.suffix.lower().lstrip(".")
        alerte_extension = None
        if detail.get("genre") == "image" and detail.get("format_reel"):
            reel = str(detail["format_reel"]).lower()
            if extension and extension not in (reel, "jpg" if reel == "jpeg" else reel):
                alerte_extension = (
                    f"l'extension « .{extension} » ne correspond pas au format "
                    f"reel du fichier ({detail['format_reel']})")

        message = self._resume(source.name, detail)
        if alerte_extension:
            message += f" ATTENTION : {alerte_extension}."

        return succes(
            action="analyser", cible=self.nom, message=message,
            preuve=f"{detail.get('genre')} lu : {source.name}",
            fichier=str(source), alerte_extension=alerte_extension, **detail)

    def _analyser_image_en_memoire(self, image_base64: str, nom_fichier: str) -> ResultatAction:
        """Meme lecture EXIF que `_analyser`, sans jamais toucher le disque.

        Aucune extension a comparer (une piece jointe n'en a pas de fiable) :
        `alerte_extension` reste toujours `None` sur ce chemin — ce n'est pas
        une omission, il n'y a rien a verifier.
        """
        import base64
        import io

        try:
            brut = base64.b64decode(image_base64, validate=False)
        except (ValueError, TypeError) as erreur:
            return echec(action="analyser", cible=self.nom,
                         message=f"Image en memoire illisible (base64 invalide) : {erreur}")

        detail = _metadata_image(io.BytesIO(brut))
        nom_affiche = nom_fichier or "(piece jointe)"
        if not detail.get("lisible"):
            return echec(
                action="analyser", cible=self.nom,
                message=(f"« {nom_affiche} » n'a pas pu etre lu comme image : "
                         f"{detail.get('erreur', 'raison inconnue')}."),
                **detail)

        return succes(
            action="analyser", cible=self.nom, message=self._resume(nom_affiche, detail),
            preuve=f"image lue en memoire : {nom_affiche}",
            fichier=None, alerte_extension=None, **detail)

    def _resume(self, nom_fichier: str, detail: Dict[str, Any]) -> str:
        genre = detail.get("genre")
        if genre == "image":
            morceaux = [f"{detail.get('format_reel')} {detail.get('largeur')}x{detail.get('hauteur')}"]
            if detail.get("modele_appareil"):
                morceaux.append(f"appareil : {detail['modele_appareil']}")
            if detail.get("date_prise"):
                morceaux.append(f"date : {detail['date_prise']}")
            if detail.get("gps_present"):
                morceaux.append("GPS present")
            return f"« {nom_fichier} » — " + ", ".join(morceaux) + "."
        if genre == "video":
            morceaux = [f"{detail.get('conteneur')}, {detail.get('codec_video')}, "
                       f"{detail.get('largeur')}x{detail.get('hauteur')}"]
            if detail.get("duree_ms"):
                morceaux.append(f"{detail['duree_ms'] / 1000:.1f}s")
            if detail.get("fps"):
                morceaux.append(f"{detail['fps']} fps")
            return f"« {nom_fichier} » — " + ", ".join(morceaux) + "."
        morceaux = [f"{detail.get('conteneur')}, {detail.get('codec')}"]
        if detail.get("duree_ms"):
            morceaux.append(f"{detail['duree_ms'] / 1000:.1f}s")
        if detail.get("echantillonnage_hz"):
            morceaux.append(f"{detail['echantillonnage_hz']} Hz")
        return f"« {nom_fichier} » — " + ", ".join(morceaux) + "."
