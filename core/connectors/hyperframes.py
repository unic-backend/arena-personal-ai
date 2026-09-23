"""Connecteur Hyperframes pour validation et rendu video HTML.

Integration originale inspiree du workflow MIT latent-spaces/brag. ARENA garde
son orchestrateur Video; Hyperframes reste un moteur de validation/rendu.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

TIMEOUT_SONDE = 45
TIMEOUT_CHECK = 180
TIMEOUT_RENDER = 900

def _commande(*args: str, cwd: Optional[Path] = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, timeout=timeout, check=False)

class ConnecteurHyperframes(Connecteur):
    service = "video_generation"
    nom = "hyperframes"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "verifier": Capacite(nom="verifier", action="read", ecriture=False,
                description="Valide une composition Hyperframes avec son browser gate reel."),
            "rendre": Capacite(nom="rendre", action="generate", ecriture=True,
                description="Rend une composition Hyperframes validee en MP4."),
        }

    def authentifier(self) -> bool:
        return True

    def sonder(self) -> Sante:
        node, ffmpeg, npx = shutil.which("node"), shutil.which("ffmpeg"), shutil.which("npx")
        manquants = [n for n, p in (("node", node), ("ffmpeg", ffmpeg), ("npx", npx)) if not p]
        if manquants:
            return Sante(EtatSante.NON_CONFIGURE, message="Prerequis Hyperframes absents.",
                         ce_qui_manque=", ".join(manquants), mesure_le=_maintenant())
        version = _commande(node, "--version", timeout=10)
        try:
            majeur = int((version.stdout or "").strip().lstrip("v").split(".", 1)[0])
        except ValueError:
            majeur = 0
        if majeur < 22:
            return Sante(EtatSante.NON_CONFIGURE, message="Node.js trop ancien.",
                         ce_qui_manque="Node.js 22+", mesure_le=_maintenant())
        try:
            doctor = _commande(npx, "--yes", "hyperframes", "doctor", "--json", timeout=TIMEOUT_SONDE)
        except (OSError, subprocess.TimeoutExpired) as erreur:
            return Sante(EtatSante.EN_PANNE, message=f"Hyperframes doctor: {type(erreur).__name__}.",
                         mesure_le=_maintenant())
        if doctor.returncode != 0:
            detail = (doctor.stderr or doctor.stdout or "doctor en echec").strip()[-500:]
            return Sante(EtatSante.NON_CONFIGURE, message=f"Hyperframes doctor refuse: {detail}",
                         ce_qui_manque="Corriger npx hyperframes doctor --json.",
                         mesure_le=_maintenant())
        return Sante(EtatSante.OPERATIONNEL, message="Hyperframes doctor repond.",
                     mesure_le=_maintenant())

    @staticmethod
    def _composition(valeur: Any) -> Optional[Path]:
        if not valeur:
            return None
        try:
            chemin = Path(str(valeur)).expanduser().resolve()
        except (OSError, RuntimeError):
            return None
        return chemin if chemin.is_dir() and (chemin / "index.html").is_file() else None

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        composition = self._composition(parametres.get("composition"))
        if composition is None:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Composition Hyperframes absente ou index.html introuvable.")
        npx = shutil.which("npx")
        if not npx:
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque="Node.js 22+ et npx")
        try:
            check = _commande(npx, "--yes", "hyperframes", "check", ".", "--json",
                              cwd=composition, timeout=TIMEOUT_CHECK)
        except subprocess.TimeoutExpired:
            return echec(action=capacite.nom, cible=self.nom, message="Hyperframes check a expire.")
        if check.returncode != 0:
            detail = (check.stdout or check.stderr or "check en echec").strip()[-2000:]
            return echec(action=capacite.nom, cible=self.nom, message=detail)
        if capacite.nom == "verifier":
            return succes(action=capacite.nom, cible=self.nom,
                          message="Composition Hyperframes validee.", preuve=str(composition))

        sortie = Path(RENDERED_DIR) / "launch-videos"
        sortie.mkdir(parents=True, exist_ok=True)
        cible = sortie / f"{composition.name}.mp4"
        try:
            rendu = _commande(npx, "--yes", "hyperframes", "render", ".", "--quality", "high",
                              "--output", str(cible), cwd=composition, timeout=TIMEOUT_RENDER)
        except subprocess.TimeoutExpired:
            return echec(action=capacite.nom, cible=self.nom, message="Rendu Hyperframes expire.")
        if rendu.returncode != 0 or not cible.is_file() or cible.stat().st_size == 0:
            detail = (rendu.stderr or rendu.stdout or "aucun fichier produit").strip()[-1200:]
            return echec(action=capacite.nom, cible=self.nom, message=f"Rendu Hyperframes echoue: {detail}")
        return succes(action=capacite.nom, cible=self.nom,
                      message="Video Hyperframes rendue et verifiee.", preuve=str(cible))
