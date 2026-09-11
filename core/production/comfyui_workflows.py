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

Un seul workflow est STABLE dans cette mission : `text_to_image`, construit
noeud par noeud a partir du JSON officiel audite
(`script_examples/basic_api_example.py` du depot ComfyUI, commit
`6338e4bd428247a4a8843496aa98fb7f2a9d3632`). Les autres (upscale,
image_to_image, controlnet, character_image, image_to_video) sont declares
CANDIDATE — leur schema et profil sont ecrits, leur gabarit ne l'est pas :
**documente, jamais invente** (mission §34, « do not just install »
appliquee a l'envers : ne pas pretendre plus que ce qui est reellement
construit).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


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

    type: str  # "str" | "int" | "float"
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
    provenance=(
        "script_examples/basic_api_example.py, ComfyUI commit "
        "6338e4bd428247a4a8843496aa98fb7f2a9d3632 (audite le 11/09/2026)."
    ),
)


def _candidat(identifiant: str, objectif: str, noeuds: Tuple[str, ...],
              vram_confortable_go: float, vram_minimum_go: float, ram_go: float,
              disque_go: float) -> EntreeWorkflow:
    """Un workflow reconnu par l'audit mais NON implemente ici — schema et
    profil ecrits pour que la mission future n'ait pas a re-auditer, gabarit
    volontairement absent (mission §34 : documenter, jamais pretendre)."""
    return EntreeWorkflow(
        identifiant=identifiant, version="0.0.0-candidate", statut=StatutWorkflow.CANDIDATE,
        objectif=objectif, noeuds_requis=noeuds,
        modeles_requis=("depend du checkpoint/adaptateur choisi a l'implementation",),
        profil_ressources=ProfilRessourcesWorkflow(
            vram_confortable_mo=int(vram_confortable_go * 1024),
            vram_minimum_mo=int(vram_minimum_go * 1024),
            ram_totale_minimum_mo=int(ram_go * 1024), disque_modele_mo=int(disque_go * 1024),
        ),
        gabarit=None,
        provenance="Identifie dans docs/audits/comfyui_audit.md — jamais implemente, jamais teste.",
    )


REGISTRE: Dict[str, EntreeWorkflow] = {
    "text_to_image": _TEXT_TO_IMAGE,
    "image_to_image": _candidat(
        "image_to_image", "Repartir d'une image source (denoise partiel).",
        ("LoadImage", "VAEEncode", "KSampler", "VAEDecode", "SaveImage"), 6, 4, 8, 4),
    "upscale": _candidat(
        "upscale", "Agrandissement par modele dedie (ESRGAN et apparentes).",
        ("LoadImage", "UpscaleModelLoader", "ImageUpscaleWithModel", "SaveImage"), 4, 2, 8, 0.2),
    "controlnet_image": _candidat(
        "controlnet_image", "Conditionnement par image de reference (ControlNet).",
        ("ControlNetLoader", "ControlNetApply", "KSampler", "VAEDecode", "SaveImage"), 8, 6, 12, 5),
    "character_image": _candidat(
        "character_image", "Image de personnage conditionnee par une reference (LoRA/adaptateur).",
        ("LoraLoader", "CLIPTextEncode", "KSampler", "VAEDecode", "SaveImage"), 7, 5, 8, 4.2),
    "image_to_video": _candidat(
        "image_to_video", "Image source vers un court clip video (modele video ComfyUI).",
        ("LoadImage", "KSamplerAdvanced", "VAEDecode", "SaveAnimatedWEBP"), 16, 10, 24, 15),
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
        vide = brut is None or (spec.type == "str" and isinstance(brut, str) and not brut.strip())
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
