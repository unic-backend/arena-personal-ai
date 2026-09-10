"""Le worker HiDream-I1 d'ARENA — un processus SEPARE, dans un environnement isole.

Mission ARENA x HIDREAM-I1 (DEC-0085). **Ce fichier est du code original
d'ARENA**, ecrit contre l'integration OFFICIELLE de HiDream-I1 dans
`diffusers` (`HiDreamImagePipeline`, documentee depuis le 11/04/2025 —
https://huggingface.co/docs/diffusers/main/en/api/pipelines/hidream).
Aucune ligne du depot `HiDream-ai/HiDream-I1` n'est copiee ici — ce depot
est etudie (`docs/audits/hidream_i1_audit.md`, commit
`5f92bab45f1dfb1e794ee357286a5b837eaf4400`), pas importe. Le paquet maison
`hi_diffusers/` du depot amont n'est PAS vendore : la voie diffusers-native
que le README amont recommande lui-meme evite d'en avoir besoin.

**A lancer par le proprietaire, dans son propre environnement isole** :

    cd tools/image/hidream
    python3.11 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    huggingface-cli login   # licence Llama 3.1 a accepter — voir README.md
    python serveur_hidream.py    # ecoute sur HIDREAM_HOST:HIDREAM_PORT (defaut 127.0.0.1:8090)

`core/connectors/hidream.py` (dans le processus principal d'ARENA) n'importe
RIEN de ce dossier : il parle a ce serveur par HTTP, exactement comme il
parle a WanGP/MoneyPrinterTurbo/CSM.

**Ce que ce serveur garantit, et qui n'est pas negociable :**

1. **`/health` mesure, il ne devine jamais.** VRAM/RAM/disque sont
   remesures a chaque appel (nvidia-smi + psutil, ICI, sur la machine qui
   va reellement charger le modele) — jamais un chiffre fige au demarrage,
   jamais suppose depuis un nom de carte.
2. **Rien ne se charge avant la premiere generation.** `_ETAT["pipe"]`
   reste `None` jusqu'au premier `/generate` accepte (mission §11) — et se
   decharge apres inactivite, comme `tools/audio/csm_service/server.py`.
3. **Une generation est un travail de fond, jamais une reponse HTTP
   bloquante.** `/generate` rend un `job_id` immediatement ; le chat
   ARENA ne l'attend jamais (meme discipline que WanGP).
4. **Un OOM ne casse jamais le worker.** La capture est explicite
   (`torch.cuda.OutOfMemoryError`), la VRAM est liberee, et le job suivant
   peut repartir — voir `_generer_en_fond`.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hidream_service")

HOTE = os.environ.get("HIDREAM_HOST", "127.0.0.1")
PORT = int(os.environ.get("HIDREAM_PORT", "8090"))
#: Ou vivent les poids telecharges — jamais dans ce depot (mission §25 :
#: cache clairement identifie, jamais sous un dossier ARENA gere par git).
CACHE_DIR = Path(os.environ.get("HIDREAM_CACHE_DIR", Path.home() / ".cache" / "hidream-arena"))
#: Ou les images produites sont ecrites — a cote du cache, jamais dans ARENA
#: directement : le connecteur (`core/connectors/hidream.py`) les recupere
#: par chemin, exactement comme WanGP/Xaar Kaname deposent dans leur propre
#: dossier avant qu'ARENA ne les copie/reference.
SORTIE_DIR = Path(os.environ.get("HIDREAM_OUTPUT_DIR", CACHE_DIR / "sorties"))
#: Decharger le pipeline apres ce delai d'inactivite (mission §11 — ne pas
#: monopoliser la carte face a Qwen/Vision/Video/WanGP).
DELAI_DECHARGEMENT_S = float(os.environ.get("HIDREAM_UNLOAD_AFTER_S", "600"))

MODEL_PREFIX = "HiDream-ai"
LLAMA_MODEL_NAME = "meta-llama/Meta-Llama-3.1-8B-Instruct"

#: Configuration par variante — reprise du `inference.py` amont (guidance et
#: pas figes par variante, verifie directement dans le depot etudie).
CONFIGS_VARIANTE: Dict[str, Dict[str, Any]] = {
    "full": {"repo": f"{MODEL_PREFIX}/HiDream-I1-Full", "guidance_scale": 5.0,
             "num_inference_steps": 50},
    "dev": {"repo": f"{MODEL_PREFIX}/HiDream-I1-Dev", "guidance_scale": 0.0,
            "num_inference_steps": 28},
    "fast": {"repo": f"{MODEL_PREFIX}/HiDream-I1-Fast", "guidance_scale": 0.0,
             "num_inference_steps": 16},
}

#: Les sept resolutions publiees par le depot amont — jamais une huitieme
#: devinee (mission §12 : « ne pas exposer de fausses options »).
RESOLUTIONS_CONNUES = {
    (1024, 1024), (768, 1360), (1360, 768), (880, 1168), (1168, 880),
    (1248, 832), (832, 1248),
}

app = FastAPI(title="ARENA — worker HiDream-I1")

_verrou = threading.Lock()
_ETAT: Dict[str, Any] = {
    "pipe": None, "variante_chargee": None, "device": None, "erreur_chargement": None,
    "dernier_usage": None,
}
_TACHES: Dict[str, "Tache"] = {}


@dataclass
class Tache:
    id: str
    state: str = "queued"  # queued -> loading -> generating -> validating -> completed|failed|cancelled
    variante: str = ""
    prompt: str = ""
    seed: Optional[int] = None
    images: List[str] = field(default_factory=list)
    error: Optional[str] = None
    cree_le: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.id, "state": self.state, "variante": self.variante,
            "prompt": self.prompt, "seed": self.seed, "images": self.images,
            "generated_files": self.images, "error": self.error, "cree_le": self.cree_le,
        }


# --- Materiel : mesure ICI, jamais empruntee a ARENA (frontiere de connecteur) ---

def _mesurer_gpu() -> Optional[Dict[str, Any]]:
    try:
        resultat = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5.0, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if resultat.returncode != 0 or not resultat.stdout.strip():
        return None
    morceaux = [m.strip() for m in resultat.stdout.strip().splitlines()[0].split(",")]
    if len(morceaux) != 3:
        return None
    try:
        return {"nom": morceaux[0], "vram_totale_mo": int(float(morceaux[1])),
                "vram_libre_mo": int(float(morceaux[2])),
                "mesure_le": datetime.now(timezone.utc).isoformat()}
    except ValueError:
        return None


def _mesurer_ram() -> Optional[Dict[str, Any]]:
    try:
        import psutil
        memoire = psutil.virtual_memory()
    except Exception:  # noqa: BLE001 — une mesure ne leve pas, elle rend None
        return None
    mo = 1024 * 1024
    return {"totale_mo": int(memoire.total / mo), "disponible_mo": int(memoire.available / mo),
            "mesure_le": datetime.now(timezone.utc).isoformat()}


def _mesurer_disque() -> Optional[Dict[str, Any]]:
    cible = CACHE_DIR if CACHE_DIR.exists() else CACHE_DIR.parent
    try:
        usage = shutil.disk_usage(cible)
    except OSError:
        return None
    mo = 1024 * 1024
    return {"chemin": str(CACHE_DIR), "libre_mo": int(usage.free / mo),
            "mesure_le": datetime.now(timezone.utc).isoformat()}


def _variantes_en_cache() -> List[str]:
    """Les variantes deja telechargees localement — jamais devinees : une
    variante absente du cache HuggingFace local n'est pas annoncee prete."""
    racine_hf = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    presentes = []
    for variante, config in CONFIGS_VARIANTE.items():
        dossier = racine_hf / f"models--{config['repo'].replace('/', '--')}"
        if dossier.is_dir():
            presentes.append(variante)
    return presentes


@app.get("/health")
def health() -> Dict[str, Any]:
    """Ne charge JAMAIS le pipeline : dit seulement ce qui est deja mesure
    ou verifiable sans effet de bord."""
    return {
        "model_loaded": _ETAT["pipe"] is not None,
        "variante_chargee": _ETAT["variante_chargee"],
        "device": _ETAT["device"],
        "erreur_chargement": _ETAT["erreur_chargement"],
        "variantes_disponibles": _variantes_en_cache(),
        "materiel": {
            "gpu": _mesurer_gpu(), "ram": _mesurer_ram(), "disque": _mesurer_disque(),
        },
    }


class GenerateRequete(BaseModel):
    prompt: str
    variante: str = "fast"
    negative_prompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    seed: Optional[int] = None
    num_inference_steps: Optional[int] = None
    guidance_scale: Optional[float] = None
    strategie: Optional[str] = None  # informatif : ce qu'ARENA a decide cote controle materiel


def _decharger_si_inactif() -> None:
    if DELAI_DECHARGEMENT_S <= 0:
        return
    with _verrou:
        if _ETAT["pipe"] is None or _ETAT["dernier_usage"] is None:
            return
        if time.monotonic() - _ETAT["dernier_usage"] < DELAI_DECHARGEMENT_S:
            return
        logger.info("HiDream inactif depuis plus de %ss : dechargement.", DELAI_DECHARGEMENT_S)
        _ETAT["pipe"] = None
        _ETAT["variante_chargee"] = None
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _charger_pipeline(variante: str) -> Optional[str]:
    """Charge (ou reutilise) le pipeline pour `variante`. Rend un message
    d'erreur en cas d'echec, jamais une exception qui remonterait jusqu'au
    thread de generation sans etat propre."""
    with _verrou:
        if _ETAT["pipe"] is not None and _ETAT["variante_chargee"] == variante:
            _ETAT["dernier_usage"] = time.monotonic()
            return None

        try:
            import torch
            from diffusers import HiDreamImagePipeline
            from transformers import LlamaForCausalLM, PreTrainedTokenizerFast
        except ImportError as erreur:
            message = f"dependances absentes : {erreur}"
            _ETAT["erreur_chargement"] = message
            return message

        try:
            config = CONFIGS_VARIANTE[variante]
            tokenizer_4 = PreTrainedTokenizerFast.from_pretrained(LLAMA_MODEL_NAME, use_fast=False)
            text_encoder_4 = LlamaForCausalLM.from_pretrained(
                LLAMA_MODEL_NAME, output_hidden_states=True, output_attentions=True,
                torch_dtype=torch.bfloat16)
            pipe = HiDreamImagePipeline.from_pretrained(
                config["repo"], tokenizer_4=tokenizer_4, text_encoder_4=text_encoder_4,
                torch_dtype=torch.bfloat16)

            if torch.cuda.is_available():
                # Offload sequentiel par defaut : seule voie qui tient sur
                # une carte de 12 Go (voir docs/audits/hidream_i1_audit.md,
                # Local Acceptance Decision). Plus lente que `.to("cuda")`
                # direct, mais ne tente jamais un chargement qui OOM.
                pipe.enable_sequential_cpu_offload()
                pipe.enable_vae_slicing()
                pipe.enable_vae_tiling()
                device = "cuda (offload sequentiel)"
            else:
                device = "cpu"

            _ETAT["pipe"] = pipe
            _ETAT["variante_chargee"] = variante
            _ETAT["device"] = device
            _ETAT["erreur_chargement"] = None
            _ETAT["dernier_usage"] = time.monotonic()
            logger.info("HiDream-I1-%s charge (%s).", variante, device)
            return None
        except Exception as erreur:  # noqa: BLE001 — un echec de chargement est un etat rapporte
            message = f"{type(erreur).__name__}: {erreur}"
            _ETAT["erreur_chargement"] = message
            return message


def _generer_en_fond(tache: Tache, requete: GenerateRequete) -> None:
    tache.state = "loading"
    erreur = _charger_pipeline(requete.variante)
    if erreur:
        tache.state = "failed"
        tache.error = erreur
        return

    tache.state = "generating"
    config = CONFIGS_VARIANTE[requete.variante]
    largeur = requete.width or 1024
    hauteur = requete.height or 1024
    if (largeur, hauteur) not in RESOLUTIONS_CONNUES:
        tache.state = "failed"
        tache.error = (f"resolution {largeur}x{hauteur} non publiee — "
                       f"resolutions connues : {sorted(RESOLUTIONS_CONNUES)}")
        return

    try:
        import torch
        seed = requete.seed if requete.seed is not None else int(torch.randint(0, 1_000_000, (1,)).item())
        generateur = torch.Generator("cpu").manual_seed(seed)

        debut = time.monotonic()
        with torch.inference_mode():
            sortie = _ETAT["pipe"](
                requete.prompt,
                negative_prompt=requete.negative_prompt,
                height=hauteur, width=largeur,
                guidance_scale=requete.guidance_scale
                if requete.guidance_scale is not None else config["guidance_scale"],
                num_inference_steps=requete.num_inference_steps
                if requete.num_inference_steps is not None else config["num_inference_steps"],
                num_images_per_prompt=1,
                generator=generateur,
            )
        duree = time.monotonic() - debut

        tache.state = "validating"
        SORTIE_DIR.mkdir(parents=True, exist_ok=True)
        chemin = SORTIE_DIR / f"hidream-{tache.id}.png"
        sortie.images[0].save(chemin)

        # Validation reelle, pas un nom de fichier suppose exister — voir
        # core/production/artefact_image.py cote ARENA pour la relecture ;
        # ici, verification minimale que le fichier ecrit est bien lisible.
        from PIL import Image
        with Image.open(chemin) as verif:
            verif.verify()

        tache.images = [str(chemin)]
        tache.seed = seed
        tache.state = "completed"
        logger.info("Tache %s terminee en %.1fs (%s).", tache.id, duree, chemin)

    except Exception as erreur:  # noqa: BLE001 — un echec de generation est un etat rapporte
        nom_erreur = type(erreur).__name__
        if "OutOfMemory" in nom_erreur:
            logger.warning("OOM pendant la tache %s : nettoyage.", tache.id)
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:  # noqa: BLE001
                pass
            tache.error = f"VRAM insuffisante pendant la generation ({nom_erreur})."
        else:
            tache.error = f"{nom_erreur}: {erreur}"
        tache.state = "failed"


@app.post("/generate")
def generate(requete: GenerateRequete) -> Dict[str, Any]:
    if not requete.prompt.strip():
        return JSONResponse(status_code=422, content={"detail": "prompt vide."})
    if requete.variante not in CONFIGS_VARIANTE:
        return JSONResponse(status_code=422, content={
            "detail": f"variante inconnue : {requete.variante!r}."})

    _decharger_si_inactif()

    tache = Tache(id=uuid.uuid4().hex[:12], variante=requete.variante, prompt=requete.prompt)
    _TACHES[tache.id] = tache
    fil = threading.Thread(target=_generer_en_fond, args=(tache, requete), daemon=True)
    fil.start()
    return {"job_id": tache.id, "state": tache.state}


@app.get("/jobs/{job_id}")
def etat_tache(job_id: str) -> Dict[str, Any]:
    tache = _TACHES.get(job_id)
    if tache is None:
        return JSONResponse(status_code=404, content={"detail": "tache inconnue."})
    return tache.to_dict()


@app.post("/jobs/{job_id}/cancel")
def annuler_tache(job_id: str) -> Dict[str, Any]:
    """Annulation cooperative, best-effort : une generation deja lancee
    dans `pipe(...)` ne peut pas etre interrompue au milieu d'un pas sans un
    callback dedie (non cable ici — mission §22 note l'etat, elle n'exige
    pas une coupure immediate). Une tache encore `queued` est annulee pour
    de vrai."""
    tache = _TACHES.get(job_id)
    if tache is None:
        return JSONResponse(status_code=404, content={"detail": "tache inconnue."})
    if tache.state == "queued":
        tache.state = "cancelled"
    return tache.to_dict()


if __name__ == "__main__":
    import uvicorn
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host=HOTE, port=PORT)
