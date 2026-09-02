"""`/api/speech/transcribe` — dictée vocale réelle (Faster-Whisper).

Avant ce fichier, la dictée du micro (composer du chat) reposait entièrement
sur la reconnaissance vocale gratuite du navigateur (Web Speech API,
`apps/pwa/src/lib/speech/index.ts`) — jamais un vrai modèle, et sans aucun
support du wolof. Demande explicite du propriétaire le 02/09/2026, en
réponse au signalement « quand je parle il écrit n'importe quoi » : « oui
vas-y pour le micro avec Whisper ».

Réutilise le transcripteur déjà chargé par `VideoAnalyzerAgent`
(`apps/backend/runtime.py:video_agent.transcriber`) plutôt que de charger un
second modèle Whisper en mémoire pour le même usage.
"""
import asyncio
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from apps.backend.runtime import video_agent
from apps.backend.security import limiter_debit, verify_api_key
from tools.audio.transcription_tool import ModeleAbsent

logger = logging.getLogger("usman.backend.speech")

router = APIRouter()

#: Une dictée est un message vocal, pas un enregistrement de plusieurs
#: heures — assez large pour ne jamais gêner un usage réel, assez étroit
#: pour ne pas remplir le disque d'un envoi anormal.
TAILLE_MAX_DICTEE = 25 * 1024 * 1024  # 25 Mo


@router.post("/api/speech/transcribe",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def transcrire_dictee(file: UploadFile = File(...), langue: str = Form("fr")) -> dict:
    contenu = await file.read()
    if not contenu:
        raise HTTPException(status_code=400, detail="Audio vide.")
    if len(contenu) > TAILLE_MAX_DICTEE:
        raise HTTPException(status_code=413, detail="Enregistrement trop long.")

    # Fichier temporaire, jamais MEDIA_DIR : une dictée n'est pas un media du
    # projet, elle est effacee juste apres, reussie ou non.
    suffixe = Path(file.filename or "dictee.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffixe, delete=False) as tampon:
        tampon.write(contenu)
        chemin = Path(tampon.name)

    try:
        # Whisper est bloquant (CPU) : hors du thread de l'event loop, sinon
        # chaque dictee gelerait le reste du serveur pendant sa duree.
        resultat = await asyncio.to_thread(
            video_agent.transcriber.transcribe, str(chemin), langue)
        return {"text": resultat["full_text"]}
    except ModeleAbsent as erreur:
        raise HTTPException(status_code=503, detail=str(erreur)) from erreur
    except Exception as erreur:  # noqa: BLE001 — un echec se rapporte, jamais un 500 muet
        logger.error("Transcription de dictee en echec : %s", erreur)
        raise HTTPException(status_code=500, detail=str(erreur)) from erreur
    finally:
        chemin.unlink(missing_ok=True)
