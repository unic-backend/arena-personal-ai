"""Studio Vidéo 1-clic : de la vidéo brute au format vertical sous-titré.

Écrit par Usman sur sa machine (`saer-video-wip`), repris ici dans la structure
en modules. La chaîne enchaîne quatre étapes réelles — analyse, transcription,
recadrage 9:16, incrustation des sous-titres — sur **la vidéo la plus récente**
trouvée dans `media/incoming/` puis, à défaut, dans `media/source/`.

Deux règles tenues par ce module :

- **Aucune vidéo trouvée n'est pas une erreur silencieuse.** La fonction dit
  quoi faire, et ne renvoie jamais un rendu imaginaire.
- **Chaque étape qui échoue est signalée**, et le rendu retourné est le dernier
  qui existe vraiment sur le disque — jamais un chemin supposé.

Les agents sont injectables : les tests font tourner la chaîne complète sans
ffmpeg, sans modèle et sans carte graphique.
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from apps.backend.config import MEDIA_DIR, RENDERED_DIR
from tools.video.nettoyage import purger_artefacts_anciens

logger = logging.getLogger("usman.backend.studio")

EXTENSIONS_VIDEO = (".mp4", ".mov", ".mkv", ".avi")

AUCUNE_VIDEO = (
    "Aucune vidéo à traiter. Envoie un MP4 avec le trombone dans LibreChat, "
    "ou dépose-le dans `media/incoming/`."
)


def derniere_video(racine: Path = MEDIA_DIR) -> Optional[Path]:
    """Rend la vidéo modifiée le plus récemment, ou `None`.

    `media/incoming/` d'abord — c'est là qu'arrivent les envois — puis
    `media/source/`. Rien n'est deviné : un dossier absent est un dossier vide.
    """
    for sous_dossier in ("incoming", "source"):
        dossier = racine / sous_dossier
        if not dossier.is_dir():
            continue
        videos = [
            fichier for fichier in dossier.iterdir()
            if fichier.is_file() and fichier.suffix.lower() in EXTENSIONS_VIDEO
        ]
        if videos:
            return max(videos, key=lambda fichier: fichier.stat().st_mtime)
    return None


async def lancer_studio(
    video_agent: Any,
    editor_agent: Any,
    subtitle_agent: Any,
    racine_media: Path = MEDIA_DIR,
    dossier_rendu: Path = RENDERED_DIR,
) -> Dict[str, Any]:
    """Traite la dernière vidéo et rend un compte rendu de ce qui a été fait.

    Le dictionnaire retourné porte `status` (`OK`, `NO_VIDEO` ou `FAILED`),
    `response` — le texte affiché dans le chat — et `etapes`, qui dit pour
    chaque étape si elle a réellement abouti.
    """
    source = derniere_video(racine_media)
    if source is None:
        logger.info("Studio : aucune video dans incoming/ ni source/")
        return {"status": "NO_VIDEO", "agent": "Studio", "response": AUCUNE_VIDEO, "etapes": {}}

    etapes: Dict[str, str] = {}

    analyse = await video_agent.run("Analyse", context={"video_path": str(source)})
    analyse = analyse if isinstance(analyse, dict) else {}
    segments = analyse.get("segments", [])
    etapes["analyse"] = "OK" if segments else "AUCUN_SEGMENT"

    mots = []
    audio = source.parent / f"{source.stem}_extracted.wav"
    if audio.exists():
        try:
            mots = video_agent.transcriber.transcribe(str(audio)).get("words", [])
            etapes["transcription"] = "OK" if mots else "AUCUN_MOT"
        except Exception as erreur:  # la transcription est optionnelle, jamais bloquante
            logger.warning(f"Studio : transcription impossible ({erreur})")
            etapes["transcription"] = "ECHEC"
    else:
        etapes["transcription"] = "PAS_D_AUDIO_EXTRAIT"

    dossier_rendu.mkdir(parents=True, exist_ok=True)
    # Purge paresseuse, avant d'ecrire : DEC-0037, aucun rendu ancien ne doit
    # s'accumuler indefiniment. Jamais bloquant.
    purger_artefacts_anciens(dossier_rendu)
    vertical = dossier_rendu / f"{source.stem}_vertical_9_16.mp4"
    editor_agent.crop_tool.convert_to_vertical_9_16(str(source), str(vertical))
    etapes["recadrage"] = "OK" if vertical.exists() else "ECHEC"

    rendu = vertical
    sous_titres = await subtitle_agent.run(
        "subs", context={"video_name": source.stem, "words": mots, "segments": segments}
    )
    sous_titres = sous_titres if isinstance(sous_titres, dict) else {}
    fichier_ass = sous_titres.get("ass_path") or sous_titres.get("srt_path") or ""

    if fichier_ass and Path(fichier_ass).exists():
        incruste = dossier_rendu / f"{source.stem}_capcut_9_16.mp4"
        if editor_agent.ffmpeg.burn_subtitles(str(rendu), fichier_ass, str(incruste)) and incruste.exists():
            rendu = incruste
            etapes["incrustation"] = "OK"
        else:
            etapes["incrustation"] = "ECHEC"
    else:
        etapes["incrustation"] = "PAS_DE_SOUS_TITRES"

    # Le chemin annoncé est celui d'un fichier qui existe, jamais un chemin supposé.
    if not rendu.exists():
        logger.warning("Studio : aucun rendu n'existe sur le disque")
        return {
            "status": "FAILED",
            "agent": "Studio",
            "response": (
                f"Le traitement de `{source.name}` n'a produit aucun fichier.\n\n"
                + "\n".join(f"- {etape} : {etat}" for etape, etat in etapes.items())
            ),
            "etapes": etapes,
        }

    return {
        "status": "OK",
        "agent": "Studio",
        "rendu": str(rendu),
        "etapes": etapes,
        "response": (
            f"**Usman Studio** — terminé\n\n"
            f"Source : `{source.name}`\n"
            f"Rendu : `{rendu.name}`\n"
            f"Emplacement : `{rendu}`\n\n"
            + "\n".join(f"- {etape} : {etat}" for etape, etat in etapes.items())
            + f"\n\n### Analyse\n{analyse.get('ai_analysis', 'Aucune analyse produite.')}"
        ),
    }
