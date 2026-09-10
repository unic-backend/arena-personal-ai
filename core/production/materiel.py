"""Materiel : ce que CETTE machine peut reellement offrir en VRAM/RAM/disque.

Mission ARENA x HIDREAM-I1 (DEC-0085). Aucune capacite lourde (HiDream, ou un
futur modele local) ne doit decider si elle peut tourner sur une supposition —
elle doit le MESURER, comme le reste d'ARENA mesure une sante de connecteur
plutot que de la deviner (`core/production/disponibilite.py`).

**Pourquoi `psutil` ici, et nulle part ailleurs dans `requirements.txt`.**
ARENA evite deliberement torch/transformers dans son environnement principal
(voir `requirements.txt`, commentaire sur `txtai_minimal`) — ce module ne les
ajoute pas. `psutil` est different en nature : une bibliotheque
d'introspection SYSTEME pure (RAM/disque), sans poids ML, et la seule facon
propre de lire la RAM disponible sur Windows ET Linux sans coder deux
chemins a la main (`ctypes.GlobalMemoryStatusEx` vs `/proc/meminfo`) — le
proprietaire du GPU tourne sous Windows (`core/connectors/xaar_kaname.py` le
montre deja via son `.venv/Scripts/python.exe`).

**La VRAM ne passe pas par `psutil`** (il ne la voit pas) : `nvidia-smi`,
deja le choix de `scripts/doctor.py` pour verifier qu'une carte NVIDIA
repond. Ce module va plus loin : il lit la memoire TOTALE et LIBRE, pas
seulement une reponse de presence.

**Rien ici n'est simule.** Sur une machine sans carte NVIDIA — celle-ci, par
exemple — `mesurer_gpu()` rend `None`, jamais un chiffre invente. Un appelant
qui a besoin d'un GPU pour decider doit traiter `None` comme « inconnu, donc
pas prouve disponible », jamais comme zero.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("usman.production.materiel")

#: Delai maximal pour `nvidia-smi` : une carte qui ne repond pas ne doit pas
#: geler l'appelant (meme discipline que les sondes de connecteur).
DELAI_NVIDIA_SMI_SECONDES = 5.0


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EtatGpu:
    """Une carte graphique NVIDIA, mesuree — jamais devinee depuis un nom de
    modele. Un `RTX A2000` peut exister sous plusieurs configurations VRAM ;
    seule la mesure reelle compte."""

    nom: str
    vram_totale_mo: int
    vram_libre_mo: int
    mesure_le: str

    def to_dict(self) -> dict:
        return {
            "nom": self.nom, "vram_totale_mo": self.vram_totale_mo,
            "vram_libre_mo": self.vram_libre_mo, "mesure_le": self.mesure_le,
        }


@dataclass
class EtatRam:
    totale_mo: int
    disponible_mo: int
    mesure_le: str

    def to_dict(self) -> dict:
        return {"totale_mo": self.totale_mo, "disponible_mo": self.disponible_mo,
                "mesure_le": self.mesure_le}


@dataclass
class EtatDisque:
    chemin: str
    libre_mo: int
    mesure_le: str

    def to_dict(self) -> dict:
        return {"chemin": self.chemin, "libre_mo": self.libre_mo, "mesure_le": self.mesure_le}


def _executer_nvidia_smi(arguments: List[str]) -> Optional[str]:
    """Lance `nvidia-smi`, rend sa sortie ou `None` — jamais une exception
    qui remonterait a un appelant qui ne s'attend qu'a « present ou pas »."""
    try:
        resultat = subprocess.run(
            ["nvidia-smi", *arguments],
            capture_output=True, text=True, timeout=DELAI_NVIDIA_SMI_SECONDES, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as erreur:
        logger.info("nvidia-smi indisponible : %s", type(erreur).__name__)
        return None
    if resultat.returncode != 0:
        return None
    return resultat.stdout.strip()


def mesurer_gpu() -> Optional[EtatGpu]:
    """La premiere carte NVIDIA que `nvidia-smi` rapporte, VRAM totale et
    libre en Mo — ou `None` si aucune carte NVIDIA n'est visible ici.

    Une seule carte est retenue (le GPU 0) : ARENA compose un seul poste de
    travail local aujourd'hui, et deviner une strategie multi-GPU sans
    machine pour la verifier serait exactement l'erreur que ce depot refuse
    ailleurs (`core/connectors/wan2gp.py`, en-tete).
    """
    sortie = _executer_nvidia_smi([
        "--query-gpu=name,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ])
    if not sortie:
        return None

    premiere_ligne = sortie.splitlines()[0]
    morceaux = [m.strip() for m in premiere_ligne.split(",")]
    if len(morceaux) != 3:
        logger.warning("Sortie nvidia-smi inattendue : %r", premiere_ligne)
        return None

    nom, total, libre = morceaux
    try:
        return EtatGpu(
            nom=nom, vram_totale_mo=int(float(total)), vram_libre_mo=int(float(libre)),
            mesure_le=_maintenant(),
        )
    except ValueError:
        logger.warning("VRAM illisible dans la sortie nvidia-smi : %r", premiere_ligne)
        return None


def mesurer_ram() -> Optional[EtatRam]:
    """RAM systeme totale et disponible, en Mo — `None` si `psutil` est
    absent ou si la mesure echoue, jamais une valeur inventee."""
    try:
        import psutil
    except ImportError:
        logger.info("psutil absent : RAM non mesurable.")
        return None

    try:
        memoire = psutil.virtual_memory()
    except Exception as erreur:  # noqa: BLE001 — une mesure ne leve pas, elle rend None
        logger.warning("Mesure RAM en echec : %s", erreur)
        return None

    mo = 1024 * 1024
    return EtatRam(
        totale_mo=int(memoire.total / mo), disponible_mo=int(memoire.available / mo),
        mesure_le=_maintenant(),
    )


def mesurer_disque(chemin: Path) -> Optional[EtatDisque]:
    """Espace libre sur le disque qui porte `chemin` — `shutil.disk_usage`
    est deja dans la bibliotheque standard, deja portable Windows/Linux.

    `chemin` peut ne pas exister encore (un dossier de cache pas encore
    cree) : c'est son PARENT existant qui est mesure, jamais une exception."""
    cible = chemin
    while not cible.exists():
        parent = cible.parent
        if parent == cible:
            logger.warning("Aucun parent existant pour mesurer le disque de %s", chemin)
            return None
        cible = parent
    try:
        usage = shutil.disk_usage(cible)
    except OSError as erreur:
        logger.warning("Mesure disque en echec pour %s : %s", cible, erreur)
        return None

    mo = 1024 * 1024
    return EtatDisque(chemin=str(chemin), libre_mo=int(usage.free / mo), mesure_le=_maintenant())
