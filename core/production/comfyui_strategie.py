"""Decider si un workflow ComfyUI peut tourner sur CETTE machine.

Mission ARENA x COMFYUI (DEC-0087). Meme discipline que
`core/production/hidream_strategie.py` : ce module ne lance jamais de
generation et ne charge jamais de poids ; il compare un
`ProfilRessourcesWorkflow` (`core/production/comfyui_workflows.py`) a un
materiel deja mesure et rend une decision, avec sa raison ecrite en clair.

**Ce qui differe de HiDream, et pourquoi la classification a six issues au
lieu de cinq.** ComfyUI gere lui-meme un « smart memory » — dechargement
automatique des poids entre VRAM et RAM des que la carte manque de place
(`comfy/model_management.py::VRAMState`, verifie dans l'audit, jamais
suppose). Un profil qui ne tient pas confortablement en VRAM peut donc
encore tourner, plus lentement, sans le controle sequentiel manuel que le
worker HiDream doit lui-meme implementer. D'ou LOCAL_FAST/LOCAL_SUPPORTED
(tient bien, ou tient) avant LOCAL_SLOW/LOCAL_OFFLOAD (tient seulement grace
au dechargement automatique) — jamais une supposition sur la vitesse
reelle, qui n'a pas ete mesuree ici (aucun GPU dans cet environnement de
developpement).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.production.comfyui_workflows import ProfilRessourcesWorkflow
from core.production.materiel import EtatDisque, EtatGpu, EtatRam

#: Memes marges de securite que hidream_strategie.py — d'autres processus
#: (Ollama, le serveur FastAPI, ComfyUI lui-meme) occupent deja une part de
#: la VRAM/RAM mesuree.
MARGE_VRAM = 0.85
MARGE_RAM = 0.80

#: VRAM residente minimale pour que le dechargement automatique de ComfyUI
#: garde une chance reelle de fonctionner — ESTIMATION documentee, jamais
#: mesuree sur un vrai GPU par ce depot.
VRAM_MO_PLANCHER_OFFLOAD_ESTIME = 2 * 1024

#: Plancher de disque libre pour ECRIRE une sortie (pas pour telecharger un
#: checkpoint : contrairement a HiDream, ComfyUI n'installe jamais un modele
#: lui-meme ici — `core/connectors/comfyui.py` refuse deja AVANT ce controle
#: si le checkpoint demande n'est pas deja present). `disque_modele_mo` du
#: profil reste documente pour l'audit (poids attendu du checkpoint), mais
#: ne gate plus cette decision : un checkpoint deja installe n'a plus besoin
#: de sa taille en disque libre pour generer.
DISQUE_MO_PLANCHER_SORTIE = 200


class StrategieComfyUI(str, Enum):
    LOCAL_FAST = "LOCAL_FAST"
    LOCAL_SUPPORTED = "LOCAL_SUPPORTED"
    LOCAL_SLOW = "LOCAL_SLOW"
    LOCAL_OFFLOAD = "LOCAL_OFFLOAD"
    REMOTE_RECOMMENDED = "REMOTE_RECOMMENDED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class Decision:
    strategie: StrategieComfyUI
    raison: str

    def to_dict(self) -> dict:
        return {"strategie": self.strategie.value, "raison": self.raison}


def _go(mo: int) -> float:
    return mo / 1024


def decider_strategie(
    profil: ProfilRessourcesWorkflow,
    gpu: Optional[EtatGpu],
    ram: Optional[EtatRam],
    disque: Optional[EtatDisque],
    *,
    worker_distant_configure: bool = False,
) -> Decision:
    """La strategie a suivre pour ce workflow, sur ce materiel.

    Args:
        profil: le profil de ressources du workflow demande.
        gpu/ram/disque: le materiel mesure (`core/production/materiel.py`,
            ou le `/system_stats` d'un ComfyUI local/distant traduit dans les
            memes types) — `None` si non mesurable, jamais zero.
        worker_distant_configure: vrai si un serveur ComfyUI distant est
            joignable (`COMFYUI_URL` non locale).
    """
    if disque is None:
        return Decision(StrategieComfyUI.UNSUPPORTED,
                        "espace disque non mesurable : rien ne peut etre ecrit en confiance.")
    if disque.libre_mo < DISQUE_MO_PLANCHER_SORTIE:
        return Decision(
            StrategieComfyUI.UNSUPPORTED,
            f"disque insuffisant pour ecrire une sortie : {_go(disque.libre_mo):.1f} Go libres, "
            f"{_go(DISQUE_MO_PLANCHER_SORTIE):.1f} Go plancher.")

    if gpu is not None and ram is not None:
        vram_utilisable_mo = gpu.vram_libre_mo * MARGE_VRAM
        ram_utilisable_mo = ram.disponible_mo * MARGE_RAM

        if (vram_utilisable_mo >= profil.vram_confortable_mo
                and ram_utilisable_mo >= profil.ram_totale_minimum_mo):
            return Decision(
                StrategieComfyUI.LOCAL_FAST,
                f"{gpu.nom} : {_go(vram_utilisable_mo):.1f} Go VRAM utilisables (marge "
                f"{MARGE_VRAM:.0%}) >= {_go(profil.vram_confortable_mo):.1f} Go confortables.")

        if (vram_utilisable_mo >= profil.vram_minimum_mo
                and ram_utilisable_mo >= profil.ram_totale_minimum_mo):
            return Decision(
                StrategieComfyUI.LOCAL_SUPPORTED,
                f"{gpu.nom} : {_go(vram_utilisable_mo):.1f} Go VRAM utilisables >= "
                f"{_go(profil.vram_minimum_mo):.1f} Go minimum, sous le seuil confortable "
                f"({_go(profil.vram_confortable_mo):.1f} Go) — plus lent, jamais mesure ici.")

        if ram_utilisable_mo >= profil.ram_totale_minimum_mo:
            if vram_utilisable_mo >= VRAM_MO_PLANCHER_OFFLOAD_ESTIME:
                return Decision(
                    StrategieComfyUI.LOCAL_OFFLOAD,
                    f"{gpu.nom} : VRAM sous le minimum ({_go(vram_utilisable_mo):.1f} Go < "
                    f"{_go(profil.vram_minimum_mo):.1f} Go) mais au-dessus du plancher de "
                    f"dechargement automatique ComfyUI estime "
                    f"({_go(VRAM_MO_PLANCHER_OFFLOAD_ESTIME):.1f} Go) — 'smart memory' "
                    "dechargera vers la RAM ; generation lente, jamais mesuree ici.")

    if worker_distant_configure:
        return Decision(
            StrategieComfyUI.REMOTE_RECOMMENDED,
            "aucune strategie locale ne tient sur ce materiel ; un serveur ComfyUI distant "
            "est configure (COMFYUI_URL) — la generation lui est deleguee.")

    raisons = []
    if gpu is None:
        raisons.append("aucune carte NVIDIA visible (nvidia-smi absent ou muet)")
    if ram is None:
        raisons.append("RAM systeme non mesurable")
    if not raisons:
        raisons.append(
            f"materiel mesure insuffisant meme pour le dechargement automatique "
            f"({_go(gpu.vram_libre_mo):.1f} Go VRAM libres, {_go(ram.totale_mo):.1f} Go RAM totale)")

    return Decision(
        StrategieComfyUI.UNSUPPORTED,
        "; ".join(raisons) + ", et aucun serveur distant n'est configure (COMFYUI_URL).")
