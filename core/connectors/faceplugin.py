"""Connecteur ARENA pour le SDK Faceplugin — analyse de visages, en local.

**Le SDK reste hors du depot.** Son depot ne porte AUCUN fichier LICENSE :
seulement un badge « Open Source » dans son README, qui ne concede rien en
droit. Sans licence explicite, tous droits reserves — copier son source dans
un depot public (DEC-0039) serait indefendable. Meme frontiere que VoiceStudio
(DEC-0027) et Xaar Kaname : un **processus separe**, appele en ligne de
commande. Le depot porte le connecteur, son pont, ses tests et son installeur.

Ce que le SDK sait faire, releve dans son `run.py` et rien de plus :
detection, reperes (landmarks), extraction de caracteristiques, similarite.
Aucune fonction inventee.

**Ce connecteur ne reconnait personne.** Il n'a pas de base de visages, il n'en
constitue pas, et il n'ecrit aucun gabarit biometrique. « Comparer » exige les
deux images dans le meme appel : il n'y a rien a interroger, donc rien a
identifier en arriere-plan.

Les deux capacites qui touchent a la **biometrie** — extraire un gabarit,
comparer deux visages — passent par la confirmation du proprietaire
(`config/permissions_services.yaml`, service `biometrie_visage`). Detecter et
placer des reperes ne dit pas QUI : ces deux-la sont des lectures.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante

#: Le SDK, installe a cote d'ARENA — jamais dedans.
FACEPLUGIN_ROOT = (
    Path(__file__).resolve().parents[2]
    / "tools" / "vision" / "faceplugin" / "Open-Source-Face-Recognition-SDK"
)

#: Son interpreteur. `torch` et `opencv` pesent plusieurs centaines de Mo et
#: n'ont rien a faire dans l'environnement d'ARENA : ils restent chez lui.
#: Windows d'abord (la machine du proprietaire), puis POSIX.
def _python_du_sdk() -> Path:
    windows = FACEPLUGIN_ROOT / ".venv" / "Scripts" / "python.exe"
    posix = FACEPLUGIN_ROOT / ".venv" / "bin" / "python"
    return windows if windows.is_file() else posix


FACEPLUGIN_RUN = FACEPLUGIN_ROOT / "run.py"

#: Le pont : du code ARENA, execute par l'interpreteur du SDK.
PONT = Path(__file__).resolve().parent / "ponts" / "faceplugin_pont.py"

#: Au-dela, le moteur est considere bloque. Une detection tient en secondes
#: sur processeur ; une minute laisse la marge d'un premier chargement de
#: modele sans laisser ARENA suspendu indefiniment.
DELAI = 120

#: Doit rester identique a `MARQUEUR` du pont : c'est le contrat entre les
#: deux, et le seul moyen de distinguer une reponse du bruit du moteur.
MARQUEUR = "@@ARENA@@"


class ConnecteurFaceplugin(Connecteur):
    """Analyse de visages par le SDK Faceplugin, en local."""

    service = "biometrie_visage"
    nom = "faceplugin"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "detecter": Capacite(
                nom="detecter",
                action="read",
                description="Compter et situer les visages d'une image.",
                ecriture=False,
            ),
            "reperes": Capacite(
                nom="reperes",
                action="read",
                description="Placer les points de repere du visage (landmarks).",
                ecriture=False,
            ),
            "caracteristiques": Capacite(
                nom="caracteristiques",
                action="biometrie",
                description="Extraire le gabarit biometrique d'un visage.",
                ecriture=True,
            ),
            "comparer": Capacite(
                nom="comparer",
                action="biometrie",
                description="Comparer deux visages et rendre leur similarite.",
                ecriture=True,
            ),
        }

    def authentifier(self) -> bool:
        return FACEPLUGIN_RUN.is_file() and _python_du_sdk().is_file()

    def sonder(self) -> Sante:
        """L'etat du moteur, mesure — pas deduit d'un dossier present.

        Trois etats, comme pour Xaar Kaname : absent n'est pas en panne.
        Le dernier controle **interroge le moteur** (il importe `run` dans son
        environnement) plutot que de conclure d'un fichier present : le SDK
        demande `torch`, `torchvision` et `opencv`, et un `.venv` existe tres
        bien sans eux.
        """
        if not FACEPLUGIN_ROOT.is_dir():
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="Faceplugin n'est pas installé.",
                ce_qui_manque=str(FACEPLUGIN_ROOT),
            )
        if not FACEPLUGIN_RUN.is_file():
            return Sante(
                etat=EtatSante.EN_PANNE,
                message="Installation incomplète : run.py absent.",
                ce_qui_manque=str(FACEPLUGIN_RUN),
            )
        python = _python_du_sdk()
        if not python.is_file():
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="Environnement Python du SDK absent.",
                ce_qui_manque=str(python),
            )

        issue = self._appeler_le_pont("sante")
        if issue.get("ok"):
            return Sante(etat=EtatSante.OPERATIONNEL, message="Faceplugin disponible.")
        return Sante(
            etat=EtatSante.EN_PANNE,
            message="Le moteur ne démarre pas.",
            ce_qui_manque=str(issue.get("erreur", ""))[:300],
        )

    def _appeler_le_pont(self, operation: str, **arguments: Any) -> Dict[str, Any]:
        """Lance le pont dans l'environnement du SDK et lit son JSON.

        `cwd` vaut la racine du SDK : ses poids sont charges par chemin
        relatif, et l'appeler d'ailleurs les rendrait introuvables.
        """
        commande = [str(_python_du_sdk()), str(PONT), operation]
        for cle, valeur in arguments.items():
            if valeur is not None:
                commande += [f"--{cle}", str(valeur)]
        try:
            processus = subprocess.run(
                commande, cwd=str(FACEPLUGIN_ROOT), capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                timeout=DELAI, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as erreur:
            return {"ok": False, "erreur": f"{type(erreur).__name__}: {erreur}"}

        # Le moteur ecrit sur la MEME sortie que le pont (« priors nums:4420 »,
        # mesure du 03/09/2026). On ne lit donc que la ligne marquee, jamais
        # tout le flux : sans cela le bavardage du SDK passait pour du JSON
        # casse et une mesure reussie se rapportait en panne.
        for ligne in (processus.stdout or "").splitlines():
            if not ligne.startswith(MARQUEUR):
                continue
            try:
                return json.loads(ligne[len(MARQUEUR):])
            except json.JSONDecodeError:
                return {"ok": False, "erreur": f"reponse illisible : {ligne[:300]}"}

        detail = (processus.stderr or processus.stdout or "").strip()[-800:]
        return {"ok": False, "erreur": detail or "le moteur n'a rien rendu"}

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        nom = capacite.nom
        if not self.authentifier():
            return non_configure(
                nom, "Faceplugin",
                f"le SDK Faceplugin n'est pas installe dans {FACEPLUGIN_ROOT}")

        image = str(parametres.get("image", "")).strip()
        if not image:
            return echec(nom, "Faceplugin", "Aucune image fournie.")
        if not Path(image).is_file():
            return echec(nom, "Faceplugin", f"Image introuvable : {image}")

        if nom == "comparer":
            image2 = str(parametres.get("image2", "")).strip()
            if not image2:
                return echec(nom, "Faceplugin",
                             "Comparer demande DEUX images : « image2 » manque.")
            if not Path(image2).is_file():
                return echec(nom, "Faceplugin", f"Seconde image introuvable : {image2}")
            issue = self._appeler_le_pont(
                "comparer", image=str(Path(image).resolve()),
                image2=str(Path(image2).resolve()))
            if not issue.get("ok"):
                return echec(nom, "Faceplugin", str(issue.get("erreur", "echec inconnu")),
                             moteur="faceplugin")
            return succes(
                nom, "Faceplugin",
                f"Similarite mesuree : {issue['score']:.1f} / 100.",
                preuve=f"{Path(image).name} ↔ {Path(image2).name}",
                score=issue["score"], echelle=issue.get("echelle"),
                moteur="faceplugin",
            )

        maximum = parametres.get("max_visages", 5)
        issue = self._appeler_le_pont(
            nom, image=str(Path(image).resolve()), max=maximum)
        if not issue.get("ok"):
            return echec(nom, "Faceplugin", str(issue.get("erreur", "echec inconnu")),
                         moteur="faceplugin")

        nombre = issue.get("nombre", 0)
        if nombre == 0:
            # **Aucun visage n'est invente.** Le moteur n'en a pas trouve : on
            # le dit comme un resultat, pas comme une panne — l'image peut
            # legitimement n'en contenir aucun.
            return succes(
                nom, "Faceplugin", "Aucun visage détecté dans cette image.",
                preuve=Path(image).name, nombre=0, moteur="faceplugin")

        detail: Dict[str, Any] = {"nombre": nombre, "moteur": "faceplugin"}
        if nom == "detecter":
            detail |= {"boites": issue.get("boites"), "scores": issue.get("scores")}
        elif nom == "reperes":
            detail |= {"reperes": issue.get("reperes")}
        else:
            detail |= {"caracteristiques": issue.get("caracteristiques")}

        return succes(
            nom, "Faceplugin",
            f"{nombre} visage(s) mesuré(s).",
            preuve=Path(image).name, **detail)
