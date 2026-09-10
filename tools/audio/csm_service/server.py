"""Le service CSM d'ARENA — un processus SEPARE, dans un environnement isole.

**Ce fichier est du code original d'ARENA**, ecrit contre l'API publique de
`transformers.CsmForConditionalGeneration` (>= 4.52.1, doc HF verifiee le
10/09/2026 : https://huggingface.co/docs/transformers/main/en/model_doc/csm).
Aucune ligne du depot `SesameAILabs/csm` n'est copiee ici — ce depot est
etudie (`docs/audits/sesame_csm_audit.md`), pas importe : voir ce meme audit
pour pourquoi l'implementation Transformers-native est preferee au runtime
original (mission §8).

**A lancer par le proprietaire, dans son propre environnement isole** :

    cd tools/audio/csm_service
    python3.10 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    huggingface-cli login   # acces gated a sesame/csm-1b ET meta-llama/Llama-3.2-1B
    python server.py        # ecoute sur CSM_URL (defaut 127.0.0.1:8901)

`core/connectors/csm.py` (dans le process principal d'ARENA) n'importe RIEN de
ce dossier : il parle a ce serveur par HTTP, exactement comme il parle a
VoiceStudio. Voir ce connecteur pour le detail de la frontiere.

**Ce que ce serveur garantit, et qui n'est pas negociable** :

1. **Le filigrane de Sesame est toujours applique** (`watermark.py`) — jamais
   une option, jamais desactivable par un parametre de requete. Une reponse
   sans filigrane verifiable n'est jamais renvoyee : `/generate` echoue
   (500) plutot que de mentir sur `X-CSM-Watermarked`.
2. **Aucun fichier audio fourni par l'appelant n'entre jamais dans un
   prompt.** Le contexte conversationnel ne grandit qu'avec de l'audio que
   CE serveur a lui-meme genere, dans la meme requete — jamais un chemin,
   jamais un upload. Voir `core/connectors/csm.py` pour pourquoi.
3. **Rien ne se charge avant le premier appel.** `_ETAT["modele"]` reste
   `None` jusqu'au premier `/generate` — pour ne pas monopoliser la carte
   graphique au demarrage (mission §14), et pour que `/health` reste rapide
   avant meme d'avoir accepte les conditions Hugging Face.
"""
from __future__ import annotations

import io
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np
import soundfile
import torch
import watermark
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("csm_service")

MODEL_ID = "sesame/csm-1b"
SAMPLE_RATE = 24000  # Mimi, verifie dans processing_csm.py de transformers.
HOTE = os.environ.get("CSM_HOST", "127.0.0.1")
PORT = int(os.environ.get("CSM_PORT", "8901"))
#: Decharger le modele apres ce delai d'inactivite (mission §14 — ne pas
#: monopoliser la carte face a Qwen/Vision/Video). 0 = ne jamais decharger.
DELAI_DECHARGEMENT_S = float(os.environ.get("CSM_UNLOAD_AFTER_S", "900"))

app = FastAPI(title="ARENA — service CSM")

_verrou = threading.Lock()
_ETAT: Dict[str, Any] = {
    "processor": None,
    "modele": None,
    "device": None,
    "device_is_accelerated": False,
    "erreur_chargement": None,
    "dernier_usage": None,
}


class TourRequete(BaseModel):
    texte: str
    speaker: int = 0


class GenerateRequete(BaseModel):
    texte: str
    speaker: int = 0
    conversation: List[TourRequete] = []
    max_audio_length_ms: int = 10_000


def _device_cible() -> tuple[str, bool]:
    """Le meilleur appareil reel, jamais suppose — meme choix que le depot
    d'origine (`run_csm.py`) : CUDA si disponible, sinon CPU. MPS ecarte
    volontairement (le README de Sesame le deconseille : « float64
    limitations »)."""
    if torch.cuda.is_available():
        return "cuda", True
    return "cpu", False


def _charger_si_besoin() -> Optional[str]:
    """Charge le modele au premier appel. Rend un message d'erreur, ou None.

    Ne leve jamais : un chargement rate est un etat (`erreur_chargement`),
    jamais un crash du service — meme discipline que le reste d'ARENA.
    """
    with _verrou:
        if _ETAT["modele"] is not None:
            return None
        if _ETAT["erreur_chargement"] is not None:
            return _ETAT["erreur_chargement"]
        try:
            from transformers import AutoProcessor, CsmForConditionalGeneration
        except ImportError as erreur:
            message = (f"transformers >= 4.52.1 n'est pas installe dans cet "
                       f"environnement isole : {erreur}")
            _ETAT["erreur_chargement"] = message
            return message

        device, accelere = _device_cible()
        try:
            processor = AutoProcessor.from_pretrained(MODEL_ID)
            modele = CsmForConditionalGeneration.from_pretrained(
                MODEL_ID, device_map=device)
        except Exception as erreur:  # noqa: BLE001 — toute cause devient un etat lisible
            message = (
                f"Chargement de {MODEL_ID} impossible : {erreur}. "
                "Verifie l'acces Hugging Face gated (huggingface-cli login, "
                "puis accepte les conditions de sesame/csm-1b ET de "
                "meta-llama/Llama-3.2-1B sur leurs pages HF).")
            logger.warning(message)
            _ETAT["erreur_chargement"] = message
            return message

        _ETAT["processor"] = processor
        _ETAT["modele"] = modele
        _ETAT["device"] = device
        _ETAT["device_is_accelerated"] = accelere
        _ETAT["dernier_usage"] = time.monotonic()
        logger.info("Modele CSM charge sur %s (accelere=%s)", device, accelere)
        return None


def _decharger_si_inactif() -> None:
    """Libere la VRAM si rien n'a demande CSM depuis `DELAI_DECHARGEMENT_S`.

    Appele au debut de chaque `/generate` : pas de thread de fond a
    surveiller separement, et le cout d'un `time.monotonic()` de plus est
    negligeable a cote d'une generation.
    """
    if DELAI_DECHARGEMENT_S <= 0:
        return
    with _verrou:
        if _ETAT["modele"] is None or _ETAT["dernier_usage"] is None:
            return
        if time.monotonic() - _ETAT["dernier_usage"] < DELAI_DECHARGEMENT_S:
            return
        logger.info("CSM inactif depuis plus de %ss : dechargement.", DELAI_DECHARGEMENT_S)
        _ETAT["modele"] = None
        _ETAT["processor"] = None
        _ETAT["erreur_chargement"] = None  # un rechargement doit pouvoir retenter
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


@app.get("/health")
def health() -> Dict[str, Any]:
    """Ne charge JAMAIS le modele : dit seulement ce qui est deja mesure."""
    return {
        "model_loaded": _ETAT["modele"] is not None,
        "device": _ETAT["device"],
        "device_is_accelerated": _ETAT["device_is_accelerated"],
        "watermarking": watermark.disponible(),
        "ce_qui_manque": _ETAT["erreur_chargement"],
    }


def _generer_un_tour(texte: str, speaker: int, contexte: List[Dict[str, Any]],
                     max_ms: int) -> np.ndarray:
    """Un seul tour, avec le contexte deja genere dans CETTE requete.

    `contexte` ne contient que des tours DEJA produits par ce meme appel
    (texte + tableau numpy audio) — jamais un fichier fourni par l'appelant.
    """
    processeur = _ETAT["processor"]
    modele = _ETAT["modele"]

    conversation = []
    for tour in contexte:
        conversation.append({
            "role": str(tour["speaker"]),
            "content": [
                {"type": "text", "text": tour["texte"]},
                {"type": "audio", "path": tour["audio"]},
            ],
        })
    conversation.append({
        "role": str(speaker),
        "content": [{"type": "text", "text": texte}],
    })

    entrees = processeur.apply_chat_template(
        conversation, tokenize=True, return_dict=True).to(modele.device)
    # `max_new_tokens` de CSM se compte en frames Mimi, pas en tokens texte —
    # meme conversion que le runtime original (`max_audio_length_ms / 80`).
    max_new_tokens = max(1, int(max_ms / 80))
    with torch.inference_mode():
        sortie = modele.generate(
            **entrees, output_audio=True, max_new_tokens=max_new_tokens)

    audio = sortie[0] if isinstance(sortie, (list, tuple)) else sortie
    if hasattr(audio, "detach"):
        audio = audio.detach().to("cpu").float()
    return audio


@app.post("/generate")
def generate(requete: GenerateRequete) -> Response:
    erreur = _charger_si_besoin()
    if erreur:
        return JSONResponse(status_code=409, content={"detail": {"message": erreur}})
    _decharger_si_inactif()
    # Un dechargement peut avoir eu lieu juste avant cette requete : verifie
    # de nouveau, recharge si besoin (l'appel precedent a juste pu tomber
    # dans une fenetre d'inactivite).
    erreur = _charger_si_besoin()
    if erreur:
        return JSONResponse(status_code=409, content={"detail": {"message": erreur}})

    with _verrou:
        _ETAT["dernier_usage"] = time.monotonic()

    texte = (requete.texte or "").strip()
    if not texte:
        return JSONResponse(status_code=400, content={"detail": "texte vide."})

    contexte: List[Dict[str, Any]] = []
    try:
        for tour in requete.conversation:
            texte_tour = (tour.texte or "").strip()
            if not texte_tour:
                continue
            audio_tour = _generer_un_tour(texte_tour, tour.speaker, contexte,
                                          requete.max_audio_length_ms)
            contexte.append({"texte": texte_tour, "speaker": tour.speaker,
                             "audio": audio_tour.numpy()})

        audio_final = _generer_un_tour(
            texte, requete.speaker, contexte, requete.max_audio_length_ms)
    except Exception as erreur:  # noqa: BLE001 — une generation ratee est un etat, pas un crash
        logger.exception("Generation CSM en echec")
        return JSONResponse(status_code=500,
                            content={"detail": f"Generation impossible : {erreur}"})

    # Regle 1 de ce module : le filigrane n'est JAMAIS optionnel. Une
    # generation dont le filigrane echoue est un ECHEC de la requete, pas un
    # fichier sans provenance renvoye quand meme.
    try:
        filigrane_ok = True
        audio_finale, debit_final = watermark.appliquer(
            audio_final, SAMPLE_RATE, _ETAT["device"])
    except Exception as erreur:  # noqa: BLE001
        logger.warning("Filigrane impossible (%s) : reponse refusee.", erreur)
        filigrane_ok = False
        audio_finale, debit_final = audio_final, SAMPLE_RATE

    if not filigrane_ok:
        return JSONResponse(
            status_code=500,
            content={"detail": "Filigrane impossible : audio non renvoye "
                                "sans provenance verifiable."})

    # `soundfile`, pas `torchaudio.save` : les versions recentes de torchaudio
    # exigent TorchCodec pour encoder (mesure directement le 10/09/2026,
    # ImportError sans lui) — la meme bibliotheque que `processor.save_audio`
    # de transformers utilise deja en interne pour ce modele.
    echantillons = audio_finale.numpy() if hasattr(audio_finale, "numpy") else audio_finale
    tampon = io.BytesIO()
    soundfile.write(tampon, echantillons, debit_final, format="WAV")
    return Response(
        content=tampon.getvalue(), media_type="audio/wav",
        headers={"X-CSM-Device": str(_ETAT["device"]),
                 "X-CSM-Watermarked": "true"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOTE, port=PORT)
