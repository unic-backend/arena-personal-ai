"""Connecteur ARENA pour Xaar Kaname / Deep-Live-Cam.

Le dépôt Deep-Live-Cam reste isolé dans tools/video/xaar_kaname/Deep-Live-Cam.
Ce connecteur communique avec son CLI headless et retourne des artefacts ARENA.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

from core.connectors.base import (
    Capacite,
    Connecteur,
    EtatSante,
    Sante,
)
from core.actions.resultat import (
    ResultatAction,
    succes,
    echec,
)


XAAR_ROOT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "video"
    / "xaar_kaname"
    / "Deep-Live-Cam"
)

XAAR_PYTHON = XAAR_ROOT / ".venv" / "Scripts" / "python.exe"
XAAR_RUN = XAAR_ROOT / "run.py"


class XaarKanameConnector(Connecteur):
    """Expose Xaar Kaname comme capacité vidéo locale d'ARENA."""

    service = "video_generation"
    nom = "xaar_kaname"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "traiter": Capacite(
                nom="traiter",
                action="generate",
                description="Traiter une image ou une vidéo avec Xaar Kaname.",
                ecriture=True,
            ),
        }

    def authentifier(self) -> bool:
        return (
            XAAR_ROOT.is_dir()
            and XAAR_PYTHON.is_file()
            and XAAR_RUN.is_file()
        )

    def sonder(self) -> Sante:
        if not XAAR_ROOT.is_dir():
            return Sante(
                etat=EtatSante.EN_PANNE,
                message="Dépôt Xaar Kaname introuvable.",
            )

        if not XAAR_PYTHON.is_file():
            return Sante(
                etat=EtatSante.EN_PANNE,
                message="Environnement Python Xaar Kaname introuvable.",
            )

        if not XAAR_RUN.is_file():
            return Sante(
                etat=EtatSante.EN_PANNE,
                message="Entrée run.py de Xaar Kaname introuvable.",
            )

        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message="Xaar Kaname disponible.",
        )

    def _executer(
        self,
        capacite: Capacite,
        **parametres: Any,
    ) -> ResultatAction:
        if capacite.nom != "traiter":
            return echec(
                "traiter",
                "Xaar Kaname",
                f"Capacité inconnue : {capacite.nom}",
            )

        source = Path(str(parametres.get("source", ""))).resolve()
        target = Path(str(parametres.get("target", ""))).resolve()
        output = Path(str(parametres.get("output", ""))).resolve()

        if not source.is_file():
            return echec(
                "traiter",
                "Xaar Kaname",
                f"Source introuvable : {source}",
            )

        if not target.is_file():
            return echec(
                "traiter",
                "Xaar Kaname",
                f"Cible introuvable : {target}",
            )

        if not str(parametres.get("output", "")).strip():
            return echec(
                "traiter",
                "Xaar Kaname",
                "Chemin de sortie obligatoire.",
            )

        output.parent.mkdir(parents=True, exist_ok=True)

        commande = [
            str(XAAR_PYTHON),
            str(XAAR_RUN),
            "--source",
            str(source),
            "--target",
            str(target),
            "--output",
            str(output),
            "--execution-provider",
            "cuda",
        ]

        if bool(parametres.get("many_faces", False)):
            commande.append("--many-faces")

        try:
            processus = subprocess.run(
                commande,
                cwd=str(XAAR_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as exc:
            return echec(
                "traiter",
                "Xaar Kaname",
                f"Impossible de lancer Xaar Kaname : {exc}",
            )

        if processus.returncode != 0:
            detail = processus.stderr.strip() or processus.stdout.strip()
            return echec(
                "traiter",
                "Xaar Kaname",
                f"Xaar Kaname a échoué (code {processus.returncode})."
                + (f" {detail[-2000:]}" if detail else ""),
            )

        if not output.is_file():
            return echec(
                "traiter",
                "Xaar Kaname",
                f"Le moteur a terminé sans produire le fichier attendu : {output}",
            )

        return succes(
            "traiter",
            "Xaar Kaname",
            f"Xaar Kaname a produit l'artefact : {output}",
            preuve=str(output),
            output=str(output),
            source=str(source),
            target=str(target),
            engine="xaar_kaname",
        )


