"""Decider si HiDream-I1 peut tourner sur CETTE machine — jamais une
supposition, toujours une comparaison a des chiffres mesures.

Mission ARENA x HIDREAM-I1 (DEC-0085). Chiffres releves directement sur le
depot HuggingFace de chaque variante (jamais empruntes a la memoire d'un
modele de langage — voir `docs/audits/hidream_i1_audit.md`) :

- **HiDream-I1-Full** : 47.2 Go sur disque
  (huggingface.co/HiDream-ai/HiDream-I1-Full, mesure le 10/09/2026) —
  transformer MoE (17B parametres au total, 4 experts routes/2 actives,
  bf16), 3 encodeurs texte, VAE.
- **HiDream-I1-Dev** : 47.2 Go (meme mesure, meme page HF de la variante Dev).
- **HiDream-I1-Fast** : meme architecture, 17B parametres confirmes sur sa
  propre page HF — retenue a la meme taille faute d'une mesure de taille
  distincte publiee.
- **`meta-llama/Meta-Llama-3.1-8B-Instruct`** (le 4e encodeur texte, EXIGE
  par les trois variantes — voir le README amont — jamais empaquete avec
  elles) : ~16 Go en bf16 (8B parametres x 2 octets, poids public connu).
  Soumis a la licence Llama 3.1 de Meta, **pas** au MIT de HiDream.

**Chaque variante charge donc environ 63 Go de poids en bf16** (47.2 + 16),
et — sans offload ni quantification — a peu pres le meme volume en VRAM
pour tourner directement sur la carte.

**Ce module ne lance jamais de generation et ne charge jamais de poids** :
il compare un profil de variante a un `Materiel` deja mesure
(`core/production/materiel.py`) et rend une decision, avec sa raison
ecrite en clair — jamais un label seul.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

from core.production.materiel import EtatDisque, EtatGpu, EtatRam

#: Marge de securite : ne jamais promettre 100 % d'une ressource mesuree.
#: D'autres processus ARENA (Ollama, le serveur FastAPI lui-meme) occupent
#: deja une part de la VRAM/RAM au moment ou HiDream voudrait charger.
MARGE_VRAM = 0.85
MARGE_RAM = 0.80

#: Diviseur retenu pour estimer le volume int4 a partir du bf16 — une
#: ESTIMATION documentee, jamais une mesure : aucune quantification n'a ete
#: verifiee sur l'architecture MoE de HiDream par ce depot (voir l'audit,
#: section Quantization). bitsandbytes/quanto compressent surtout les
#: couches lineaires ; VAE et normalisations restent en precision plus
#: haute, d'ou un facteur < 4 malgre l'int4.
DIVISEUR_QUANTIFICATION_ESTIME = 3.5

#: VRAM residente minimale estimee pour un offload CPU sequentiel (une
#: couche/activation a la fois sur la carte). Estimation documentee, pas
#: mesuree : aucun essai reel n'a eu lieu sur ce depot faute de GPU
#: disponible ici.
VRAM_GO_OFFLOAD_SEQUENTIEL_ESTIME = 6.0


class StrategieHiDream(str, Enum):
    LOCAL_FULL = "LOCAL_FULL"
    LOCAL_QUANTIZED = "LOCAL_QUANTIZED"
    LOCAL_OFFLOAD = "LOCAL_OFFLOAD"
    REMOTE_REQUIRED = "REMOTE_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class ProfilVariante:
    """Ce qu'une variante HiDream-I1 exige reellement, mesure sur HuggingFace."""

    nom: str
    disque_go: float
    vram_go_bf16: float
    ram_go_minimum: float

    @property
    def vram_go_quantifie_estime(self) -> float:
        return round(self.vram_go_bf16 / DIVISEUR_QUANTIFICATION_ESTIME, 1)


#: Les trois variantes reellement publiees (README amont) — jamais une
#: quatrieme devinee.
PROFILS: Dict[str, ProfilVariante] = {
    "full": ProfilVariante("full", disque_go=63.2, vram_go_bf16=63.2, ram_go_minimum=16.0),
    "dev": ProfilVariante("dev", disque_go=63.2, vram_go_bf16=63.2, ram_go_minimum=16.0),
    "fast": ProfilVariante("fast", disque_go=63.2, vram_go_bf16=63.2, ram_go_minimum=16.0),
}


@dataclass
class Decision:
    strategie: StrategieHiDream
    raison: str

    def to_dict(self) -> dict:
        return {"strategie": self.strategie.value, "raison": self.raison}


def _go(mo: int) -> float:
    return mo / 1024


def decider_strategie(
    profil: ProfilVariante,
    gpu: Optional[EtatGpu],
    ram: Optional[EtatRam],
    disque: Optional[EtatDisque],
    *,
    worker_distant_configure: bool = False,
) -> Decision:
    """La strategie a suivre pour generer avec `profil`, sur ce materiel.

    Args:
        profil: la variante visee (`PROFILS["full"|"dev"|"fast"]`).
        gpu: la carte mesuree (`materiel.mesurer_gpu()`), ou `None` si
            aucune carte NVIDIA n'est visible — traite comme « pas prouve
            disponible », jamais comme zero.
        ram: la RAM systeme mesuree, ou `None` si la mesure a echoue.
        disque: l'espace disque mesure sur le dossier de cache des modeles,
            ou `None` si la mesure a echoue.
        worker_distant_configure: vrai si un worker HiDream distant est
            joignable (`HIDREAM_WORKER_URL` non locale) — decide entre
            REMOTE_REQUIRED et UNSUPPORTED quand le local ne suffit pas.

    Returns:
        Une `Decision` — jamais un label seul, toujours sa raison.
    """
    if disque is None:
        return Decision(StrategieHiDream.UNSUPPORTED,
                        "espace disque non mesurable : rien ne peut etre telecharge en confiance.")
    if disque.libre_mo < 0 or _go(disque.libre_mo) < profil.disque_go:
        manquant = profil.disque_go - _go(disque.libre_mo)
        return Decision(
            StrategieHiDream.UNSUPPORTED,
            f"disque insuffisant pour {profil.nom} : {_go(disque.libre_mo):.1f} Go libres, "
            f"{profil.disque_go:.1f} Go requis ({manquant:.1f} Go manquants).")

    if gpu is not None and ram is not None:
        vram_utilisable = _go(gpu.vram_libre_mo) * MARGE_VRAM
        ram_utilisable = _go(ram.disponible_mo) * MARGE_RAM

        if vram_utilisable >= profil.vram_go_bf16 and ram_utilisable >= profil.ram_go_minimum:
            return Decision(
                StrategieHiDream.LOCAL_FULL,
                f"{gpu.nom} : {vram_utilisable:.1f} Go VRAM utilisables (marge {MARGE_VRAM:.0%}) "
                f">= {profil.vram_go_bf16:.1f} Go requis en bf16 sans offload.")

        if vram_utilisable >= profil.vram_go_quantifie_estime and ram_utilisable >= profil.ram_go_minimum:
            return Decision(
                StrategieHiDream.LOCAL_QUANTIZED,
                f"{gpu.nom} : {vram_utilisable:.1f} Go VRAM utilisables insuffisants pour le "
                f"bf16 complet ({profil.vram_go_bf16:.1f} Go) mais couvrent l'estimation "
                f"quantifiee ({profil.vram_go_quantifie_estime:.1f} Go, diviseur "
                f"{DIVISEUR_QUANTIFICATION_ESTIME} — ESTIME, jamais verifie sur cette "
                "architecture MoE par ce depot).")

        if (vram_utilisable >= VRAM_GO_OFFLOAD_SEQUENTIEL_ESTIME
                and _go(ram.totale_mo) >= profil.disque_go):
            return Decision(
                StrategieHiDream.LOCAL_OFFLOAD,
                f"{gpu.nom} : VRAM insuffisante meme quantifiee, mais "
                f"{vram_utilisable:.1f} Go >= {VRAM_GO_OFFLOAD_SEQUENTIEL_ESTIME:.1f} Go "
                "(estimation d'offload CPU sequentiel) et la RAM totale "
                f"({_go(ram.totale_mo):.1f} Go) peut porter les {profil.disque_go:.1f} Go de "
                "poids dechargеs — generation tres lente attendue, jamais mesuree ici.")

    if worker_distant_configure:
        return Decision(
            StrategieHiDream.REMOTE_REQUIRED,
            "aucune strategie locale ne tient sur ce materiel ; un worker HiDream distant "
            "est configure (HIDREAM_WORKER_URL) — la generation lui est deleguee.")

    raison_materiel = []
    if gpu is None:
        raison_materiel.append("aucune carte NVIDIA visible (nvidia-smi absent ou muet)")
    if ram is None:
        raison_materiel.append("RAM systeme non mesurable")
    if not raison_materiel:
        raison_materiel.append(
            f"materiel mesure insuffisant pour {profil.nom} meme quantifie/offload "
            f"({_go(gpu.vram_libre_mo):.1f} Go VRAM libres, {_go(ram.totale_mo):.1f} Go RAM totale)")

    return Decision(
        StrategieHiDream.UNSUPPORTED,
        "; ".join(raison_materiel) + ", et aucun worker distant n'est configure "
        "(HIDREAM_WORKER_URL).")
