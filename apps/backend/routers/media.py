"""Envoi de fichiers et chaine de production video.

L'envoi est controle sur trois points : le type, la taille, et le fait qu'un
refus ne laisse rien sur le disque.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from apps.backend.config import (
    EXTENSIONS_MEDIA_AUTORISEES,
    MEDIA_DIR,
    RENDERED_DIR,
    TAILLE_BLOC_ENVOI,
    TAILLE_MAX_ENVOI,
)
from apps.backend.pieces_jointes import nom_de_fichier_sur
from apps.backend.runtime import clip_selector, editor_agent, permissions, subtitle_agent, video_agent
from apps.backend.security import limiter_debit, verify_api_key
from tools.video.nettoyage import purger_artefacts_anciens

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

    # `Path(...).name` seul ne suffit pas : sur Linux, le `\\` de Windows n'est
    # pas un separateur, donc « C:\\Users\\Saer\\clip.mp4 » revenait ENTIER et
    # devenait un nom de fichier absurde dans `incoming/`. Le proprietaire est
    # sous Windows, son serveur sous Linux : c'est le cas courant, pas un cas
    # limite. `nom_de_fichier_sur` (apps/backend/pieces_jointes.py) coupe deja
    # les deux separateurs — reutilise plutot que redit ici.
    nom_sur = nom_de_fichier_sur(nom_brut)
    if not nom_sur or nom_sur in {".", "..", "sans-nom"}:
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

    `destination` est reclamee de facon ATOMIQUE (`"xb"`, `O_EXCL`) : si un
    autre envoi tient deja ce chemin, `open()` leve `FileExistsError` avant
    qu'un seul octet ne soit ecrit — jamais un `"wb"` qui aurait tronque
    silencieusement le fichier de quelqu'un d'autre en l'ouvrant (audit
    externe, commit f7f0478 : un second envoi du meme nom ecrasait le
    premier, et un echec ensuite supprimait meme ce qui restait). L'appelant
    (`upload_video`) essaie un autre nom sur `FileExistsError` — jamais cette
    fonction, qui ne sait rien du reste du dossier.
    """
    taille = 0
    try:
        with open(destination, "xb") as tampon:
            while bloc := await file.read(TAILLE_BLOC_ENVOI):
                taille += len(bloc)
                if taille > TAILLE_MAX_ENVOI:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fichier trop volumineux (maximum "
                               f"{TAILLE_MAX_ENVOI / (1024 ** 3):.1f} Go)."
                    )
                tampon.write(bloc)
    except FileExistsError:
        # `destination` appartient a un AUTRE envoi (fini, ou encore en
        # cours) : rien n'a ete ouvert par CET appel, donc rien a nettoyer —
        # un `unlink` ici supprimerait le fichier de cet autre envoi.
        raise
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    if taille == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Fichier vide.")

    return taille


def _candidats_de_nom(nom_sur: str):
    """Le nom d'origine d'abord — cas courant, garde lisible et compatible
    avec tout ce qui l'attend deja (`medias_montables`, l'inventaire des
    references cote PWA) — puis des variantes numerotees seulement si ce
    nom est deja pris. Jamais un nom invente qui perdrait le nom d'origine :
    `chantier_2.mp4` reste lisible a cote de `chantier.mp4`."""
    yield nom_sur
    tige, suffixe = Path(nom_sur).stem, Path(nom_sur).suffix
    compteur = 1
    while True:
        yield f"{tige}_{compteur}{suffixe}"
        compteur += 1


#: Personne ne depose jamais mille fichiers de suite sous le meme nom ; au-dela,
#: continuer a essayer serait masquer un vrai probleme (dossier non nettoye,
#: boucle d'envoi emballee) derriere une attente silencieuse.
LIMITE_TENTATIVES_NOM = 1000


@router.post("/api/upload", dependencies=[Depends(verify_api_key)])
async def upload_video(file: UploadFile = File(...)):
    try:
        if not permissions.is_allowed("WRITE_FILES"):
            raise HTTPException(status_code=403, detail="Écriture non autorisée.")

        safe_filename = valider_nom_de_fichier(file.filename)
        incoming_dir = MEDIA_DIR / "incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)

        # Chaque candidat est reclame de facon ATOMIQUE par `ecrire_par_blocs`
        # (`FileExistsError` sur collision) : jamais un `.exists()` verifie
        # puis un chemin different pris entre-temps par un envoi concurrent —
        # l'ecriture elle-meme est la reclamation (audit externe, commit
        # f7f0478 : deux envois du meme nom, l'un ecrasait l'autre).
        file_path = None
        stored_filename = None
        taille = None
        for tentative, candidat in enumerate(_candidats_de_nom(safe_filename)):
            if tentative >= LIMITE_TENTATIVES_NOM:
                raise HTTPException(
                    status_code=507,
                    detail=f"Impossible de trouver un nom de stockage libre pour "
                           f"'{safe_filename}' apres {LIMITE_TENTATIVES_NOM} essais."
                )
            file_path = incoming_dir / candidat
            try:
                taille = await ecrire_par_blocs(file, file_path)
            except FileExistsError:
                continue
            stored_filename = candidat
            break

        logger.info(f"Fichier reçu : {stored_filename} ({taille / (1024 ** 2):.1f} Mo)"
                   + (f" — nom d'origine '{safe_filename}' deja pris" if stored_filename != safe_filename else ""))

        return {
            "status": "success",
            "filename": stored_filename,
            # Le nom d'origine (nettoye), pour l'afficher meme quand une
            # collision a force un nom de stockage different — jamais perdu.
            "original_filename": safe_filename,
            "path": str(file_path),
            "size_bytes": taille,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur upload: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

def _srt_si_reel(sub_res: Any) -> str:
    """Le chemin du fichier de sous-titres, s'il existe vraiment sur le
    disque. Un chemin annonce sans fichier derriere est une fausse reussite
    de plus, meme si la video, elle, est bien la."""
    chemin = sub_res.get("srt_path") if isinstance(sub_res, dict) else None
    if chemin and Path(chemin).exists() and Path(chemin).stat().st_size > 0:
        return str(chemin)
    return ""


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
        # Un `clip_path` rendu par le selecteur n'est pas une preuve : trouve
        # le 12/09/2026 en diagnostiquant ce meme correctif, ce chemin-ci
        # court-circuitait toute verification des lors que le fichier
        # EXISTAIT — un extrait vide ou tronque partait en "status":
        # "success" avec son URL. Meme exigence que pour le rendu de repli
        # ci-dessous : existe, non vide, et un vrai flux video (ffprobe).
        if rendered_file_path and Path(rendered_file_path).exists():
            if not editor_agent.crop_tool._sortie_est_valide(Path(rendered_file_path)):
                logger.warning(
                    "Extrait rendu par le selecteur invalide (%s) : on repasse "
                    "par le rendu 9:16 plutot que de l'annoncer pret.",
                    rendered_file_path)
                rendered_file_path = None
        if not rendered_file_path or not Path(rendered_file_path).exists():
            # Purge paresseuse, avant d'ecrire : DEC-0037, aucun rendu ancien
            # ne doit s'accumuler indefiniment dans RENDERED_DIR.
            purger_artefacts_anciens(RENDERED_DIR)
            target_rendered = RENDERED_DIR / f"{p.stem}_vertical_9_16.mp4"
            reussi = editor_agent.crop_tool.convert_to_vertical_9_16(str(p), str(target_rendered))
            # Avant ce correctif, ce retour etait ignore : `False` (ffmpeg
            # indisponible, rendu tronque) n'empechait jamais d'annoncer
            # "status": "success" avec une URL qui pointait sur un fichier
            # absent ou invalide (audit externe, commit f7f0478).
            # `convert_to_vertical_9_16` verifie deja son propre fichier
            # (existence, taille, flux video reel via ffprobe) ; ceci est
            # une seconde lecture au point d'usage, jamais une confiance
            # aveugle dans son retour.
            if not reussi or not target_rendered.exists() or target_rendered.stat().st_size == 0:
                return {"status": "error",
                        "message": "Le rendu 9:16 a echoue : aucun fichier valide produit."}
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
            # Un chemin SRT annonce mais absent du disque est la meme
            # fausse reussite en plus petit : on ne le rapporte que s'il
            # existe reellement (12/09/2026).
            "subtitle_srt": _srt_si_reel(sub_res),
            "ai_summary": analysis_res.get("ai_analysis") if isinstance(analysis_res, dict) else ""
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur pipeline vidéo: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
