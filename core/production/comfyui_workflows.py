"""Le registre CONTROLE des workflows ComfyUI approuves — mission ARENA x
COMFYUI (DEC-0087).

ComfyUI accepte n'importe quel graphe JSON qu'on lui poste sur `/prompt`
(voir `docs/audits/comfyui_audit.md`, section API). **ARENA n'expose jamais
ce graphe brut a un appelant** : la mission l'interdit explicitement
(§8/§9/§30 — « do not create hundreds of uncontrolled JSON files », « do not
accept arbitrary external workflow JSON and execute it blindly »).

Ce module est donc la SEULE porte : un identifiant de workflow + des
parametres valides, jamais un graphe libre. Chaque entree porte :

- un **schema d'entree** ferme (parametres nommes, types, bornes) —
  `valider_parametres` refuse tout ce qui n'y figure pas ;
- un **gabarit** deterministe qui construit le JSON « API format » exact
  qu'audite `docs/audits/comfyui_audit.md` — jamais un texte de prompt
  injecte a une position arbitraire du graphe (mission §9) ;
- un **profil de ressources** ESTIME (jamais mesure sur un vrai GPU dans cet
  environnement de developpement — meme honnetete que
  `core/production/hidream_strategie.py`) ;
- un **statut de cycle de vie** (mission §48) : CANDIDATE (declare, gabarit
  pas encore ecrit ou pas encore teste), TESTE (gabarit ecrit, teste sans
  serveur reel), STABLE (promu — seul statut que le connecteur accepte
  d'executer).

Les six workflows sont STABLE : `text_to_image` (mission initiale, DEC-0087)
puis `image_to_image`, `upscale`, `controlnet_image`, `character_image` et
`image_to_video` (suite de la mission, meme jour), chacun reconstruit noeud
par noeud a partir des classes NODE reelles du depot ComfyUI audite (`nodes.py`,
`comfy_extras/nodes_upscale_model.py`, `comfy_extras/nodes_video_model.py`,
commit `6338e4bd428247a4a8843496aa98fb7f2a9d3632`) — jamais devine depuis un
nom de noeud plausible. Le meme critere que `text_to_image` : un gabarit
construit noeud par noeud contre le SCHEMA REEL (`INPUT_TYPES`/`define_schema`
du code source), teste deterministiquement, jamais confirme contre un
serveur ComfyUI reellement lance (aucun GPU dans cet environnement de
developpement — meme limite que `text_to_image` et que HiDream, DEC-0085).

**Une image d'entree ne touche jamais le disque cote ARENA.** Les quatre
workflows qui prennent une image de reference (`image_to_image`, `upscale`,
`controlnet_image`) declarent leur parametre en `type="image_base64"` —
memes octets en memoire que `apps/backend/pieces_jointes.py` pour une pièce
jointe (DEC-0019) : jamais un chemin de fichier local, jamais de lecture
arbitraire sur le disque du serveur (mission §31 — le risque que ce depot a
deja corrige une fois, `agents/plaquiste/plaquiste_agent.py
::chemin_hors_du_depot`, ici evite structurellement plutot que filtre apres
coup). Le connecteur (`core/connectors/comfyui.py`) decode ces octets et les
televerse a ComfyUI via `POST /upload/image` avant de construire la requete —
ce module reste lui-meme sans reseau, seulement une validation de forme
(taille, base64 valide).
"""
from __future__ import annotations

import base64
import binascii
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

#: Plafond de taille d'une image de reference DECODEE — sanite avant tout
#: envoi, pas une limite ComfyUI. Meme ordre de grandeur que
#: `apps/backend/pieces_jointes.py::TAILLE_MAX_OCTETS`, jamais importe
#: directement : `core/production/` ne depend pas de `apps/backend/`.
TAILLE_IMAGE_MAX_OCTETS = 20 * 1024 * 1024


class StatutWorkflow(str, Enum):
    CANDIDATE = "CANDIDATE"
    TESTE = "TESTED"
    STABLE = "STABLE"


@dataclass(frozen=True)
class ProfilRessourcesWorkflow:
    """Ce qu'un workflow exige, ESTIME — jamais mesure sur un vrai GPU ici.

    Les seuils sont deliberement conservateurs et documentes comme des
    estimations : aucune carte NVIDIA n'est disponible dans cet
    environnement de developpement (meme limite que DEC-0085).
    """

    vram_confortable_mo: int
    vram_minimum_mo: int
    ram_totale_minimum_mo: int
    disque_modele_mo: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vram_confortable_mo": self.vram_confortable_mo,
            "vram_minimum_mo": self.vram_minimum_mo,
            "ram_totale_minimum_mo": self.ram_totale_minimum_mo,
            "disque_modele_mo": self.disque_modele_mo,
        }


@dataclass(frozen=True)
class ParametreWorkflow:
    """Un parametre du schema d'entree — le seul vocabulaire qu'un appelant
    peut utiliser pour ce workflow."""

    type: str  # "str" | "int" | "float" | "image_base64"
    requis: bool = False
    defaut: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type, "requis": self.requis, "defaut": self.defaut,
            "minimum": self.minimum, "maximum": self.maximum,
        }


Gabarit = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class EntreeWorkflow:
    """Un workflow approuve — jamais un graphe libre."""

    identifiant: str
    version: str
    statut: StatutWorkflow
    objectif: str
    noeuds_requis: Tuple[str, ...]
    modeles_requis: Tuple[str, ...]
    profil_ressources: ProfilRessourcesWorkflow
    schema_entree: Dict[str, ParametreWorkflow] = field(default_factory=dict)
    gabarit: Optional[Gabarit] = None
    provenance: str = ""
    #: parametre -> dossier de modeles ComfyUI (`GET /models/{dossier}`) a
    #: verifier avant tout envoi — generalise le controle « le checkpoint
    #: demande est-il installe ? » au-dela de `ckpt_name`/`checkpoints`
    #: (mission §12/§25 : jamais un telechargement automatique, donc jamais
    #: un essai sans avoir verifie que le modele existe deja).
    verification_modeles: Dict[str, str] = field(default_factory=dict)

    @property
    def implemente(self) -> bool:
        return self.gabarit is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifiant": self.identifiant, "version": self.version,
            "statut": self.statut.value, "objectif": self.objectif,
            "noeuds_requis": list(self.noeuds_requis),
            "modeles_requis": list(self.modeles_requis),
            "profil_ressources": self.profil_ressources.to_dict(),
            "schema_entree": {cle: p.to_dict() for cle, p in self.schema_entree.items()},
            "implemente": self.implemente,
            "provenance": self.provenance,
        }


# --- text_to_image : le seul workflow STABLE ---------------------------------

def _gabarit_text_to_image(p: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruit exactement le JSON « API format » audite dans
    `script_examples/basic_api_example.py` (ComfyUI, commit
    `6338e4bd428247a4a8843496aa98fb7f2a9d3632`) : memes neuf noeuds, memes
    identifiants, seuls les `inputs` varient avec les parametres valides."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": p["cfg"], "denoise": 1, "latent_image": ["5", 0], "model": ["4", 0],
                "negative": ["7", 0], "positive": ["6", 0], "sampler_name": "euler",
                "scheduler": "normal", "seed": p["seed"], "steps": p["steps"],
            },
        },
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": p["ckpt_name"]}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": p["height"], "width": p["width"]},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": p["prompt"]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": p["negative_prompt"]},
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "arena", "images": ["8", 0]},
        },
    }


_TEXT_TO_IMAGE = EntreeWorkflow(
    identifiant="text_to_image",
    version="1.0.0",
    statut=StatutWorkflow.STABLE,
    objectif="Texte vers image, un checkpoint de diffusion standard (SD1.x/SDXL).",
    noeuds_requis=(
        "KSampler", "CheckpointLoaderSimple", "EmptyLatentImage", "CLIPTextEncode",
        "VAEDecode", "SaveImage",
    ),
    modeles_requis=("un checkpoint .safetensors installe dans ComfyUI (models/checkpoints/)",),
    # ESTIME pour un checkpoint SD1.5-like (~4 Go) a 512x512 : ordre de grandeur
    # public largement documente, jamais mesure sur un GPU par ce depot.
    profil_ressources=ProfilRessourcesWorkflow(
        vram_confortable_mo=6 * 1024, vram_minimum_mo=4 * 1024,
        ram_totale_minimum_mo=8 * 1024, disque_modele_mo=4 * 1024,
    ),
    schema_entree={
        "prompt": ParametreWorkflow(type="str", requis=True),
        "negative_prompt": ParametreWorkflow(type="str", requis=False, defaut=""),
        "width": ParametreWorkflow(type="int", requis=False, defaut=512, minimum=64, maximum=2048),
        "height": ParametreWorkflow(type="int", requis=False, defaut=512, minimum=64, maximum=2048),
        "steps": ParametreWorkflow(type="int", requis=False, defaut=20, minimum=1, maximum=150),
        "cfg": ParametreWorkflow(type="float", requis=False, defaut=8.0, minimum=0.0, maximum=30.0),
        "seed": ParametreWorkflow(type="int", requis=False, defaut=None),
        "ckpt_name": ParametreWorkflow(type="str", requis=True),
    },
    gabarit=_gabarit_text_to_image,
    verification_modeles={"ckpt_name": "checkpoints"},
    provenance=(
        "script_examples/basic_api_example.py, ComfyUI commit "
        "6338e4bd428247a4a8843496aa98fb7f2a9d3632 (audite le 11/09/2026)."
    ),
)


# --- image_to_image : repartir d'une image source, denoise partiel ------------

def _gabarit_image_to_image(p: Dict[str, Any]) -> Dict[str, Any]:
    """`LoadImage` (audite `nodes.py:1738`) prend le nom que ComfyUI a rendu
    apres televersement (`POST /upload/image` — le connecteur substitue),
    jamais la chaine base64 elle-meme. `VAEEncode` (`nodes.py:380`, inputs
    `pixels`/`vae`) remplace `EmptyLatentImage` ; `KSampler.denoise` (< 1)
    controle combien de l'image source survit — audite sur la signature
    reelle de `common_ksampler`, jamais suppose."""
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": p["image_source"]}},
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": p["ckpt_name"]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": p["prompt"]}},
        "4": {"class_type": "CLIPTextEncode",
             "inputs": {"clip": ["2", 1], "text": p["negative_prompt"]}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["1", 0], "vae": ["2", 2]}},
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": p["cfg"], "denoise": p["denoise"], "latent_image": ["5", 0],
                "model": ["2", 0], "negative": ["4", 0], "positive": ["3", 0],
                "sampler_name": "euler", "scheduler": "normal", "seed": p["seed"],
                "steps": p["steps"],
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["2", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"filename_prefix": "arena", "images": ["7", 0]}},
    }


_IMAGE_TO_IMAGE = EntreeWorkflow(
    identifiant="image_to_image",
    version="1.0.0",
    statut=StatutWorkflow.STABLE,
    objectif="Repartir d'une image source (denoise partiel) plutot que d'un bruit pur.",
    noeuds_requis=(
        "LoadImage", "CheckpointLoaderSimple", "CLIPTextEncode", "VAEEncode", "KSampler",
        "VAEDecode", "SaveImage",
    ),
    modeles_requis=("un checkpoint .safetensors installe dans ComfyUI (models/checkpoints/)",),
    profil_ressources=ProfilRessourcesWorkflow(
        vram_confortable_mo=6 * 1024, vram_minimum_mo=4 * 1024,
        ram_totale_minimum_mo=8 * 1024, disque_modele_mo=4 * 1024,
    ),
    schema_entree={
        "prompt": ParametreWorkflow(type="str", requis=True),
        "negative_prompt": ParametreWorkflow(type="str", requis=False, defaut=""),
        "image_source": ParametreWorkflow(type="image_base64", requis=True),
        "denoise": ParametreWorkflow(type="float", requis=False, defaut=0.75, minimum=0.0, maximum=1.0),
        "steps": ParametreWorkflow(type="int", requis=False, defaut=20, minimum=1, maximum=150),
        "cfg": ParametreWorkflow(type="float", requis=False, defaut=8.0, minimum=0.0, maximum=30.0),
        "seed": ParametreWorkflow(type="int", requis=False, defaut=None),
        "ckpt_name": ParametreWorkflow(type="str", requis=True),
    },
    gabarit=_gabarit_image_to_image,
    verification_modeles={"ckpt_name": "checkpoints"},
    provenance=(
        "nodes.py (LoadImage:1738, VAEEncode:380, KSampler:1592-ish via common_ksampler), "
        "ComfyUI commit 6338e4bd428247a4a8843496aa98fb7f2a9d3632 (audite le 11/09/2026)."
    ),
)


# --- upscale : agrandissement par modele dedie ---------------------------------

def _gabarit_upscale(p: Dict[str, Any]) -> Dict[str, Any]:
    """`UpscaleModelLoader`/`ImageUpscaleWithModel`
    (`comfy_extras/nodes_upscale_model.py:20,52`) — aucun texte, aucun
    checkpoint de diffusion : une pure operation image-a-image par un
    modele dedie (ESRGAN et apparentes)."""
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": p["image_source"]}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": p["model_name"]}},
        "3": {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]},
        },
        "4": {"class_type": "SaveImage", "inputs": {"filename_prefix": "arena", "images": ["3", 0]}},
    }


_UPSCALE = EntreeWorkflow(
    identifiant="upscale",
    version="1.0.0",
    statut=StatutWorkflow.STABLE,
    objectif="Agrandissement par modele dedie (ESRGAN et apparentes) — jamais de texte.",
    noeuds_requis=("LoadImage", "UpscaleModelLoader", "ImageUpscaleWithModel", "SaveImage"),
    modeles_requis=("un modele d'agrandissement installe (models/upscale_models/)",),
    # Un modele ESRGAN-like est bien plus leger qu'un checkpoint de diffusion
    # complet ; VRAM dominee par la resolution de l'image d'entree, pas le
    # modele — plancher prudent, jamais mesure sur un vrai GPU ici.
    profil_ressources=ProfilRessourcesWorkflow(
        vram_confortable_mo=4 * 1024, vram_minimum_mo=2 * 1024,
        ram_totale_minimum_mo=6 * 1024, disque_modele_mo=256,
    ),
    schema_entree={
        "image_source": ParametreWorkflow(type="image_base64", requis=True),
        "model_name": ParametreWorkflow(type="str", requis=True),
    },
    gabarit=_gabarit_upscale,
    verification_modeles={"model_name": "upscale_models"},
    provenance=(
        "comfy_extras/nodes_upscale_model.py (UpscaleModelLoader:20, "
        "ImageUpscaleWithModel:52), commit 6338e4bd428247a4a8843496aa98fb7f2a9d3632 "
        "(audite le 11/09/2026)."
    ),
)


# --- controlnet_image : conditionnement par image de reference -----------------

def _gabarit_controlnet_image(p: Dict[str, Any]) -> Dict[str, Any]:
    """`ControlNetApplyAdvanced` (`nodes.py:930`), jamais l'ancien
    `ControlNetApply` — marque `DEPRECATED = True` dans le code source
    audite. Rend `(positive, negative)` modifies ; `KSampler` les consomme
    comme n'importe quelle paire de conditionnements."""
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": p["image_source"]}},
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": p["ckpt_name"]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": p["prompt"]}},
        "4": {"class_type": "CLIPTextEncode",
             "inputs": {"clip": ["2", 1], "text": p["negative_prompt"]}},
        "5": {"class_type": "ControlNetLoader",
             "inputs": {"control_net_name": p["control_net_name"]}},
        "6": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["3", 0], "negative": ["4", 0], "control_net": ["5", 0],
                "image": ["1", 0], "strength": p["strength"], "start_percent": 0.0,
                "end_percent": 1.0,
            },
        },
        "7": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": p["height"], "width": p["width"]},
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": p["cfg"], "denoise": 1, "latent_image": ["7", 0], "model": ["2", 0],
                "negative": ["6", 1], "positive": ["6", 0], "sampler_name": "euler",
                "scheduler": "normal", "seed": p["seed"], "steps": p["steps"],
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["2", 2]}},
        "10": {"class_type": "SaveImage", "inputs": {"filename_prefix": "arena", "images": ["9", 0]}},
    }


_CONTROLNET_IMAGE = EntreeWorkflow(
    identifiant="controlnet_image",
    version="1.0.0",
    statut=StatutWorkflow.STABLE,
    objectif="Conditionnement par image de reference (ControlNet) — pose/contours/profondeur.",
    noeuds_requis=(
        "LoadImage", "CheckpointLoaderSimple", "CLIPTextEncode", "ControlNetLoader",
        "ControlNetApplyAdvanced", "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage",
    ),
    modeles_requis=(
        "un checkpoint .safetensors (models/checkpoints/) et un modele ControlNet "
        "(models/controlnet/) installes dans ComfyUI",
    ),
    profil_ressources=ProfilRessourcesWorkflow(
        vram_confortable_mo=8 * 1024, vram_minimum_mo=6 * 1024,
        ram_totale_minimum_mo=12 * 1024, disque_modele_mo=5 * 1024,
    ),
    schema_entree={
        "prompt": ParametreWorkflow(type="str", requis=True),
        "negative_prompt": ParametreWorkflow(type="str", requis=False, defaut=""),
        "image_source": ParametreWorkflow(type="image_base64", requis=True),
        "control_net_name": ParametreWorkflow(type="str", requis=True),
        "strength": ParametreWorkflow(type="float", requis=False, defaut=1.0, minimum=0.0, maximum=10.0),
        "width": ParametreWorkflow(type="int", requis=False, defaut=512, minimum=64, maximum=2048),
        "height": ParametreWorkflow(type="int", requis=False, defaut=512, minimum=64, maximum=2048),
        "steps": ParametreWorkflow(type="int", requis=False, defaut=20, minimum=1, maximum=150),
        "cfg": ParametreWorkflow(type="float", requis=False, defaut=8.0, minimum=0.0, maximum=30.0),
        "seed": ParametreWorkflow(type="int", requis=False, defaut=None),
        "ckpt_name": ParametreWorkflow(type="str", requis=True),
    },
    gabarit=_gabarit_controlnet_image,
    verification_modeles={"ckpt_name": "checkpoints", "control_net_name": "controlnet"},
    provenance=(
        "nodes.py (ControlNetLoader:866, ControlNetApplyAdvanced:930 — "
        "ControlNetApply:901 est DEPRECATED, delibirement evite), commit "
        "6338e4bd428247a4a8843496aa98fb7f2a9d3632 (audite le 11/09/2026)."
    ),
)


# --- character_image : LoRA/adaptateur sur un checkpoint standard --------------

def _gabarit_character_image(p: Dict[str, Any]) -> Dict[str, Any]:
    """`LoraLoader` (`nodes.py:709`) module le MODEL et le CLIP du checkpoint
    de base — jamais une image de reference (mission §17 : le routeur
    compose des capacites existantes, il ne reimplemente pas
    l'identite/reference d'un personnage ARENA, deja portee par
    `core/production/personnage_video.py`, DEC-0084)."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": p["ckpt_name"]}},
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0], "clip": ["1", 1], "lora_name": p["lora_name"],
                "strength_model": p["strength_model"], "strength_clip": p["strength_clip"],
            },
        },
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": p["prompt"]}},
        "4": {"class_type": "CLIPTextEncode",
             "inputs": {"clip": ["2", 1], "text": p["negative_prompt"]}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": p["height"], "width": p["width"]},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": p["cfg"], "denoise": 1, "latent_image": ["5", 0], "model": ["2", 0],
                "negative": ["4", 0], "positive": ["3", 0], "sampler_name": "euler",
                "scheduler": "normal", "seed": p["seed"], "steps": p["steps"],
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"filename_prefix": "arena", "images": ["7", 0]}},
    }


_CHARACTER_IMAGE = EntreeWorkflow(
    identifiant="character_image",
    version="1.0.0",
    statut=StatutWorkflow.STABLE,
    objectif="Image de personnage conditionnee par un adaptateur LoRA sur un checkpoint standard.",
    noeuds_requis=(
        "CheckpointLoaderSimple", "LoraLoader", "CLIPTextEncode", "EmptyLatentImage",
        "KSampler", "VAEDecode", "SaveImage",
    ),
    modeles_requis=(
        "un checkpoint .safetensors (models/checkpoints/) et un adaptateur LoRA "
        "(models/loras/) installes dans ComfyUI",
    ),
    profil_ressources=ProfilRessourcesWorkflow(
        vram_confortable_mo=7 * 1024, vram_minimum_mo=5 * 1024,
        ram_totale_minimum_mo=8 * 1024, disque_modele_mo=int(4.2 * 1024),
    ),
    schema_entree={
        "prompt": ParametreWorkflow(type="str", requis=True),
        "negative_prompt": ParametreWorkflow(type="str", requis=False, defaut=""),
        "ckpt_name": ParametreWorkflow(type="str", requis=True),
        "lora_name": ParametreWorkflow(type="str", requis=True),
        "strength_model": ParametreWorkflow(
            type="float", requis=False, defaut=1.0, minimum=-100.0, maximum=100.0),
        "strength_clip": ParametreWorkflow(
            type="float", requis=False, defaut=1.0, minimum=-100.0, maximum=100.0),
        "width": ParametreWorkflow(type="int", requis=False, defaut=512, minimum=64, maximum=2048),
        "height": ParametreWorkflow(type="int", requis=False, defaut=512, minimum=64, maximum=2048),
        "steps": ParametreWorkflow(type="int", requis=False, defaut=20, minimum=1, maximum=150),
        "cfg": ParametreWorkflow(type="float", requis=False, defaut=8.0, minimum=0.0, maximum=30.0),
        "seed": ParametreWorkflow(type="int", requis=False, defaut=None),
    },
    gabarit=_gabarit_character_image,
    verification_modeles={"ckpt_name": "checkpoints", "lora_name": "loras"},
    provenance=(
        "nodes.py (LoraLoader:709), commit 6338e4bd428247a4a8843496aa98fb7f2a9d3632 "
        "(audite le 11/09/2026)."
    ),
)


# --- image_to_video : SVD, la seule voie video native de ComfyUI ---------------

def _gabarit_image_to_video(p: Dict[str, Any]) -> Dict[str, Any]:
    """Stable Video Diffusion, seule famille video que ComfyUI expede en
    natif (`comfy_extras/nodes_video_model.py`, verifie dans l'audit —
    aucun autre modele video n'est cable dans le depot lui-meme).
    `ImageOnlyCheckpointLoader` (VAE + CLIP_VISION, pas de texte : un
    checkpoint SVD n'a pas d'encodeur texte) -> `SVD_img2vid_Conditioning`
    (rend positive/negative/latent) -> `VideoLinearCFGGuidance` (patch le
    modele) -> `KSamplerAdvanced` -> `VAEDecode` -> `SaveAnimatedWEBP`."""
    return {
        "1": {"class_type": "ImageOnlyCheckpointLoader", "inputs": {"ckpt_name": p["ckpt_name"]}},
        "2": {"class_type": "LoadImage", "inputs": {"image": p["image_source"]}},
        "3": {
            "class_type": "SVD_img2vid_Conditioning",
            "inputs": {
                "clip_vision": ["1", 1], "init_image": ["2", 0], "vae": ["1", 2],
                "width": p["width"], "height": p["height"], "video_frames": p["video_frames"],
                "motion_bucket_id": p["motion_bucket_id"], "fps": p["fps"],
                "augmentation_level": p["augmentation_level"],
            },
        },
        "4": {"class_type": "VideoLinearCFGGuidance",
             "inputs": {"model": ["1", 0], "min_cfg": p["min_cfg"]}},
        "5": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["4", 0], "add_noise": "enable", "noise_seed": p["seed"],
                "steps": p["steps"], "cfg": p["cfg"], "sampler_name": "euler",
                "scheduler": "karras", "positive": ["3", 0], "negative": ["3", 1],
                "latent_image": ["3", 2], "start_at_step": 0, "end_at_step": 10000,
                "return_with_leftover_noise": "disable",
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["6", 0], "filename_prefix": "arena", "fps": p["fps"],
                "lossless": True, "quality": 80, "method": "default",
            },
        },
    }


_IMAGE_TO_VIDEO = EntreeWorkflow(
    identifiant="image_to_video",
    version="1.0.0",
    statut=StatutWorkflow.STABLE,
    objectif="Image source vers un court clip video (Stable Video Diffusion, natif ComfyUI).",
    noeuds_requis=(
        "ImageOnlyCheckpointLoader", "LoadImage", "SVD_img2vid_Conditioning",
        "VideoLinearCFGGuidance", "KSamplerAdvanced", "VAEDecode", "SaveAnimatedWEBP",
    ),
    modeles_requis=("un checkpoint SVD (models/checkpoints/, ex. svd_xt.safetensors)",),
    # SVD est bien plus lourd qu'un checkpoint image standard (video latente
    # multi-frames) — estimation prudente, jamais mesuree sur un vrai GPU ici.
    profil_ressources=ProfilRessourcesWorkflow(
        vram_confortable_mo=16 * 1024, vram_minimum_mo=10 * 1024,
        ram_totale_minimum_mo=24 * 1024, disque_modele_mo=15 * 1024,
    ),
    schema_entree={
        "image_source": ParametreWorkflow(type="image_base64", requis=True),
        "ckpt_name": ParametreWorkflow(type="str", requis=True),
        "width": ParametreWorkflow(type="int", requis=False, defaut=1024, minimum=64, maximum=2048),
        "height": ParametreWorkflow(type="int", requis=False, defaut=576, minimum=64, maximum=2048),
        "video_frames": ParametreWorkflow(type="int", requis=False, defaut=14, minimum=1, maximum=4096),
        "motion_bucket_id": ParametreWorkflow(
            type="int", requis=False, defaut=127, minimum=1, maximum=1023),
        "fps": ParametreWorkflow(type="int", requis=False, defaut=6, minimum=1, maximum=1024),
        "augmentation_level": ParametreWorkflow(
            type="float", requis=False, defaut=0.0, minimum=0.0, maximum=10.0),
        "min_cfg": ParametreWorkflow(type="float", requis=False, defaut=1.0, minimum=0.0, maximum=100.0),
        "steps": ParametreWorkflow(type="int", requis=False, defaut=20, minimum=1, maximum=10000),
        "cfg": ParametreWorkflow(type="float", requis=False, defaut=2.5, minimum=0.0, maximum=100.0),
        "seed": ParametreWorkflow(type="int", requis=False, defaut=None),
    },
    gabarit=_gabarit_image_to_video,
    verification_modeles={"ckpt_name": "checkpoints"},
    provenance=(
        "comfy_extras/nodes_video_model.py (ImageOnlyCheckpointLoader, "
        "SVD_img2vid_Conditioning, VideoLinearCFGGuidance), nodes.py "
        "(KSamplerAdvanced:1626), commit 6338e4bd428247a4a8843496aa98fb7f2a9d3632 "
        "(audite le 11/09/2026)."
    ),
)


REGISTRE: Dict[str, EntreeWorkflow] = {
    "text_to_image": _TEXT_TO_IMAGE,
    "image_to_image": _IMAGE_TO_IMAGE,
    "upscale": _UPSCALE,
    "controlnet_image": _CONTROLNET_IMAGE,
    "character_image": _CHARACTER_IMAGE,
    "image_to_video": _IMAGE_TO_VIDEO,
}


def lister() -> List[Dict[str, Any]]:
    """Le catalogue entier — ce que `/api/image/workflows` et le modele
    voient. Jamais le gabarit lui-meme (mission §47 : l'identifiant et les
    parametres, pas le graphe complet, dans le contexte du modele)."""
    return [entree.to_dict() for entree in REGISTRE.values()]


def obtenir(identifiant: str) -> Optional[EntreeWorkflow]:
    return REGISTRE.get(identifiant)


@dataclass
class ResultatValidation:
    ok: bool
    erreurs: List[str] = field(default_factory=list)
    parametres: Dict[str, Any] = field(default_factory=dict)


def _coercer(nom: str, spec: ParametreWorkflow, valeur: Any) -> Tuple[Optional[Any], Optional[str]]:
    if spec.type == "image_base64":
        return _valider_image_base64(nom, valeur)

    try:
        if spec.type == "int":
            coerce = int(valeur)
        elif spec.type == "float":
            coerce = float(valeur)
        else:
            coerce = str(valeur)
    except (TypeError, ValueError):
        return None, f"{nom} : « {valeur} » n'est pas un {spec.type} valide."

    if spec.minimum is not None and coerce < spec.minimum:
        return None, f"{nom} : {coerce} est sous le minimum ({spec.minimum})."
    if spec.maximum is not None and coerce > spec.maximum:
        return None, f"{nom} : {coerce} depasse le maximum ({spec.maximum})."
    return coerce, None


def _valider_image_base64(nom: str, valeur: Any) -> Tuple[Optional[Any], Optional[str]]:
    """Verifie la FORME d'une image de reference — base64 valide, taille
    raisonnable une fois decodee — jamais son contenu (`valider_image` du
    connecteur, apres televersement, fait ce travail-la sur les SORTIES ;
    ici il n'y a encore rien a ouvrir comme image, seulement des octets).

    Ne touche jamais le reseau ni le disque : `construire_requete` ne recoit
    QUE la chaine base64 d'origine (le connecteur decode et televerse), donc
    ce module reste testable sans serveur (mission §9)."""
    if not isinstance(valeur, str) or not valeur.strip():
        return None, f"{nom} : image de reference absente."
    try:
        decode = base64.b64decode(valeur, validate=True)
    except (binascii.Error, ValueError):
        return None, f"{nom} : n'est pas du base64 valide."
    if not decode:
        return None, f"{nom} : image de reference vide une fois decodee."
    if len(decode) > TAILLE_IMAGE_MAX_OCTETS:
        return None, (f"{nom} : image de {len(decode) / (1024 * 1024):.1f} Mo, "
                      f"plafond {TAILLE_IMAGE_MAX_OCTETS // (1024 * 1024)} Mo.")
    return valeur, None


def valider_parametres(identifiant: str, parametres: Dict[str, Any]) -> ResultatValidation:
    """Valide et coerce `parametres` contre le schema du workflow.

    Deterministe et testable SANS serveur ComfyUI (mission §9) : aucune
    valeur n'est envoyee tant que cette fonction n'a pas rendu `ok=True`.
    """
    entree = obtenir(identifiant)
    if entree is None:
        return ResultatValidation(False, [f"workflow inconnu : « {identifiant} »."])
    if not entree.implemente:
        return ResultatValidation(
            False, [f"workflow « {identifiant} » reconnu mais pas implemente "
                   f"(statut {entree.statut.value}) — aucun gabarit a construire."])

    erreurs: List[str] = []
    valeurs: Dict[str, Any] = {}
    for nom, spec in entree.schema_entree.items():
        brut = parametres.get(nom, spec.defaut)
        vide = brut is None or (spec.type in ("str", "image_base64")
                                and isinstance(brut, str) and not brut.strip())
        if vide:
            if spec.requis:
                erreurs.append(f"{nom} : parametre requis absent.")
            else:
                valeurs[nom] = brut if not isinstance(brut, str) else brut
            continue
        coerce, erreur = _coercer(nom, spec, brut)
        if erreur:
            erreurs.append(erreur)
        else:
            valeurs[nom] = coerce

    inconnus = set(parametres) - set(entree.schema_entree)
    if inconnus:
        erreurs.append(
            f"parametre(s) non reconnu(s) pour « {identifiant} » : {', '.join(sorted(inconnus))}.")

    if erreurs:
        return ResultatValidation(False, erreurs)

    # Le seed n'est jamais laisse a None vers le gabarit : ComfyUI exige un
    # entier. Un appelant qui n'en fournit pas obtient un tirage reel, rendu
    # dans les parametres coerces pour que la provenance le rapporte —
    # jamais une reproductibilite qui n'a pas ete demandee.
    if valeurs.get("seed") is None and "seed" in entree.schema_entree:
        valeurs["seed"] = random.randint(0, 2**32 - 1)

    return ResultatValidation(True, [], valeurs)


def construire_requete(identifiant: str, parametres_valides: Dict[str, Any]) -> Dict[str, Any]:
    """Rend le JSON « API format » ComfyUI — jamais appele sans etre passe
    par `valider_parametres` d'abord (le connecteur applique cette regle)."""
    entree = obtenir(identifiant)
    if entree is None or entree.gabarit is None:
        raise ValueError(f"workflow non constructible : « {identifiant} ».")
    return entree.gabarit(parametres_valides)
