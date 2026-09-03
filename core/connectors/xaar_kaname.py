"""Connecteur ARENA pour Xaar Kaname / Deep-Live-Cam.

Le dépôt Deep-Live-Cam reste isolé dans tools/video/xaar_kaname/Deep-Live-Cam.
Ce connecteur communique avec son CLI headless et retourne des artefacts ARENA.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

from core.actions.resultat import (
    ResultatAction,
    echec,
    succes,
)
from core.connectors.base import (
    Capacite,
    Connecteur,
    EtatSante,
    Sante,
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
        """L'état du moteur, mesuré sur le disque.

        **Trois états, pas deux, et la distinction est celle qui compte pour
        qui lit le diagnostic :**

        - le dossier n'existe pas → `NON_CONFIGURE`. Rien n'est cassé : le
          moteur n'est simplement pas installé. C'est déjà ce que rapportent
          WanGP, MoneyPrinterTurbo, VoiceStudio et OpenTakeoff quand ils sont
          absents. Le dire `EN_PANNE` enverrait le propriétaire réparer une
          installation qui n'a jamais existé.
        - le dossier existe mais `.venv` ou `run.py` manque → `EN_PANNE`.
          Là une installation a commencé et n'est pas allée au bout : il y a
          bien quelque chose à réparer.
        - tout est là → `OPERATIONNEL`.

        `ce_qui_manque` porte le chemin exact, parce qu'un « introuvable »
        sans le chemin cherché n'aide personne à savoir où regarder.
        """
        if not XAAR_ROOT.is_dir():
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="Xaar Kaname n'est pas installé.",
                ce_qui_manque=str(XAAR_ROOT),
            )

        if not XAAR_PYTHON.is_file():
            return Sante(
                etat=EtatSante.EN_PANNE,
                message="Installation incomplète : environnement Python absent.",
                ce_qui_manque=str(XAAR_PYTHON),
            )

        if not XAAR_RUN.is_file():
            return Sante(
                etat=EtatSante.EN_PANNE,
                message="Installation incomplète : run.py absent.",
                ce_qui_manque=str(XAAR_RUN),
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


