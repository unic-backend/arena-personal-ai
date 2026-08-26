"""Envoi de fichiers et chaine de production video.

L'envoi est controle sur trois points : le type, la taille, et le fait qu'un
refus ne laisse rien sur le disque.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from apps.backend.config import (
    EXTENSIONS_MEDIA_AUTORISEES,
    MEDIA_DIR,
    RENDERED_DIR,
    TAILLE_BLOC_ENVOI,
    TAILLE_MAX_ENVOI,
)
from apps.backend.runtime import clip_selector, editor_agent, permissions, subtitle_agent, video_agent
from apps.backend.security import limiter_debit, verify_api_key

logger = logging.getLogger("usman.backend")

router = APIRouter()


# ==============================================================================
# ENDPOINTS MÉDIAS & PIPELINES
# ==============================================================================
def valider_nom_de_fichier(nom_brut: Optional[str]) -> str:
    """Verifie le nom d'un fichier envoye et renvoie un nom sur.

    Deux controles distincts : `Path(...).name` neutralise la traversee de
    repertoire, la liste blanche d'extensions decide de ce qu'Usman accepte.
    """
    if not nom_brut or not nom_brut.strip():
        raise HTTPException(status_code=400, detail="Nom de fichier manquant.")

    nom_sur = Path(nom_brut).name
    if not nom_sur or nom_sur in {".", ".."}:
        raise HTTPException(status_code=400, detail="Nom de fichier invalide.")

    extension = Path(nom_sur).suffix.lower()
    if extension not in EXTENSIONS_MEDIA_AUTORISEES:
        autorisees = ", ".join(sorted(EXTENSIONS_MEDIA_AUTORISEES))
        # Guillemets imbriques interdits dans une f-string avant Python 3.12.
        libelle = extension or "aucune extension"
        raise HTTPException(
            status_code=415,
            detail=f"Type de fichier non autorise : '{libelle}'. "
                   f"Formats acceptes : {autorisees}."
        )
    return nom_sur


async def ecrire_par_blocs(file: UploadFile, destination: Path) -> int:
    """Ecrit le fichier bloc par bloc et renvoie sa taille.

    Depasser le plafond interrompt l'ecriture et supprime le fichier partiel :
    un envoi refuse ne doit rien laisser sur le disque.
    """
    taille = 0
    try:
        with open(destination, "wb") as tampon:
            while bloc := await file.read(TAILLE_BLOC_ENVOI):
                taille += len(bloc)
                if taille > TAILLE_MAX_ENVOI:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fichier trop volumineux (maximum "
                               f"{TAILLE_MAX_ENVOI / (1024 ** 3):.1f} Go)."
                    )
                tampon.write(bloc)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    if taille == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Fichier vide.")

    return taille


@router.post("/api/upload", dependencies=[Depends(verify_api_key)])
async def upload_video(file: UploadFile = File(...)):
    try:
        if not permissions.is_allowed("WRITE_FILES"):
            raise HTTPException(status_code=403, detail="Écriture non autorisée.")

        safe_filename = valider_nom_de_fichier(file.filename)
        incoming_dir = MEDIA_DIR / "incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)

        file_path = incoming_dir / safe_filename
        taille = await ecrire_par_blocs(file, file_path)
        logger.info(f"Fichier reçu : {safe_filename} ({taille / (1024 ** 2):.1f} Mo)")

        return {
            "status": "success",
            "filename": safe_filename,
            "path": str(file_path),
            "size_bytes": taille,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur upload: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/api/process-video", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def process_video_pipeline(video_path: str = Form(...)):
    try:
        p = Path(video_path).resolve()
        try:
            p.relative_to(MEDIA_DIR.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Accès refusé.") from None

        if not p.exists():
            return {"status": "error", "message": f"Fichier introuvable: {video_path}"}

        analysis_res = await video_agent.run("Analyse complète", context={"video_path": str(p)})
        segments = analysis_res.get("segments", []) if isinstance(analysis_res, dict) else []

        clip_res = await clip_selector.run("Isole le meilleur extrait viral", context={
            "video_path": str(p),
            "segments": segments
        })

        rendered_file_path = clip_res.get("clip_path") if isinstance(clip_res, dict) else None
        if not rendered_file_path or not Path(rendered_file_path).exists():
            target_rendered = RENDERED_DIR / f"{p.stem}_vertical_9_16.mp4"
            editor_agent.crop_tool.convert_to_vertical_9_16(str(p), str(target_rendered))
            rendered_file_path = str(target_rendered)

        sub_res = await subtitle_agent.run("Génère sous-titres", context={
            "video_name": p.stem,
            "segments": segments
        })

        rendered_p = Path(rendered_file_path)
        video_web_url = f"/media/rendered/{rendered_p.name}"

        return {
            "status": "success",
            "video_original": p.name,
            "rendered_9_16": str(rendered_p),
            "video_web_url": video_web_url,
            "subtitle_srt": sub_res.get("srt_path") if isinstance(sub_res, dict) else "",
            "ai_summary": analysis_res.get("ai_analysis") if isinstance(analysis_res, dict) else ""
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur pipeline vidéo: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
