"""Aucun moteur externe n'entre dans le dépôt. La raison change, la règle non.

Ce dépôt est **public** (DEC-0039). Chaque moteur externe reste à côté d'ARENA,
et le dépôt ne porte que son connecteur, ses tests et son installeur. La règle
existait pour VoiceStudio (DEC-0027), WanGP, MoneyPrinterTurbo et Xaar Kaname ;
`tests/test_xaar_kaname_reste_dehors.py` la mesurait pour un seul d'entre eux.

Deux moteurs s'ajoutent le 03/09/2026, **pour deux raisons différentes** :

- **Faceplugin** n'a aucun fichier `LICENSE`. Son README affiche un badge
  « Open Source », qui ne concède rien en droit. Sans licence explicite : tous
  droits réservés. Son source ne peut pas entrer ici, et son `.venv` pèse
  1,1 Go (torch, opencv).
- **UI/UX Pro Max** est MIT : rien n'interdirait de le versionner. Il reste
  dehors **par convention**. Une seule règle pour tous les moteurs vaut mieux
  que deux règles selon la licence — c'est la seconde qu'on oublie d'appliquer.

`test_la_regle_vaut_pour_tous_les_moteurs` est celui qui compte : il ne croit
aucune intention écrite, il **mesure** que rien de ces moteurs n'est dans git.
"""
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

#: Chaque moteur, son dossier, et ce qu'un clone y pose de plus lourd ou de
#: plus sensible.
MOTEURS = {
    # Xaar Kaname / Deep-Live-Cam : **AGPL-3.0**, et `LICENSE` d'ARENA dit
    # « All rights reserved ». Faire entrer son source ferait d'ARENA une
    # oeuvre derivee, donc publiable sous AGPL — sur un depot public.
    # (Ces controles vivaient dans `test_xaar_kaname_reste_dehors.py`, fondu
    # ici le 03/09/2026 : deux fichiers mesuraient la meme regle du depot et
    # pouvaient diverger. Aucune assertion n'a ete perdue.)
    "tools/video/xaar_kaname": (
        "Deep-Live-Cam/.venv/Lib/site-packages/onnxruntime/capi/cudnn64_9.dll",
        "Deep-Live-Cam/models/inswapper_128.onnx",
        "Deep-Live-Cam/run.py",
        "Deep-Live-Cam/modules/core.py",
        "Deep-Live-Cam/arena_xaar_final.jpg",
        "Deep-Live-Cam/output.mp4",
    ),
    "tools/vision/faceplugin": (
        "Open-Source-Face-Recognition-SDK/.venv/lib/python3.11/site-packages/torch/_C.so",
        "Open-Source-Face-Recognition-SDK/run.py",
        "Open-Source-Face-Recognition-SDK/face_detect/models/pretrained/version-slim-320.pth",
        "Open-Source-Face-Recognition-SDK/test/1.jpg",
    ),
    "tools/design/ui_ux_pro_max": (
        "src/ui-ux-pro-max/scripts/search.py",
        "src/ui-ux-pro-max/data/styles.csv",
        "cli/node_modules/quelque-chose.js",
    ),
    # Lean 4 (DEC-0067) : **Apache-2.0**, donc rien n'interdirait de le
    # versionner — il reste dehors par convention, comme UI/UX Pro Max, et
    # parce qu'un toolchain decompresse pese 2,9 Go. Un depot public ne porte
    # pas un compilateur.
    "tools/formel": (
        "lean/bin/lean",
        "lean/lib/lean/library/Init/Prelude.olean",
        "lean/bin/lake",
    ),
}


def _est_ignore(chemin: str) -> bool:
    """Git ignorerait-il ce chemin ? La question est posée à git, pas déduite."""
    return subprocess.run(
        ["git", "check-ignore", "-q", chemin],
        cwd=RACINE, capture_output=True, check=False,
    ).returncode == 0


@pytest.mark.parametrize(
    "chemin",
    [f"{dossier}/{relatif}"
     for dossier, relatifs in MOTEURS.items() for relatif in relatifs])
def test_rien_dun_moteur_externe_ne_peut_entrer(chemin):
    assert _est_ignore(chemin), (
        f"{chemin} entrerait dans un depot PUBLIC : source sans licence, "
        "modele lourd, environnement Python ou image de test.")


@pytest.mark.parametrize("dossier", list(MOTEURS))
def test_le_dossier_du_moteur_est_ignore_en_entier(dossier):
    """Une règle par extension oublierait toujours le fichier suivant."""
    assert _est_ignore(f"{dossier}/un_fichier_qu_on_n_a_pas_prevu.bin")


@pytest.mark.parametrize("dossier", list(MOTEURS))
def test_aucun_fichier_du_moteur_nest_deja_suivi(dossier):
    """Une règle d'ignore n'a **aucun effet** sur un fichier déjà suivi.

    Si l'un était entré avant la règle, il y resterait sans que rien ne le
    dise — et c'est le seul cas où l'ignore donne une fausse assurance.
    """
    suivis = subprocess.run(
        ["git", "ls-files", dossier],
        cwd=RACINE, capture_output=True, text=True, check=False,
    ).stdout.split()

    assert suivis == [], f"deja dans git : {suivis}"


def test_la_regle_vaut_pour_tous_les_moteurs():
    """Sept moteurs, une règle, mesurée — pas crue sur parole.

    Ce que le dépôt porte pour chacun : le connecteur, ses tests, son
    installeur, et pour Faceplugin un pont (du code ARENA qui appelle le SDK
    sans en copier une ligne).
    """
    suivis = subprocess.run(
        ["git", "ls-files"], cwd=RACINE, capture_output=True, text=True, check=False,
    ).stdout.splitlines()

    autorises = ("docs/", "scripts/installer_", "core/connectors/", "tests/")
    for moteur in ("Deep-Live-Cam", "VoiceStudio", "WanGP", "MoneyPrinterTurbo",
                   "Faceplugin", "ui-ux-pro-max", "ui_ux_pro_max"):
        dedans = [f for f in suivis
                  if moteur.lower() in f.lower() and not f.startswith(autorises)]
        assert dedans == [], f"du source de {moteur} est versionne : {dedans}"


@pytest.mark.parametrize("dossier,mot", [
    ("tools/video/xaar_kaname", "agpl"),
    ("tools/vision/faceplugin", "licence"),
    ("tools/design/ui_ux_pro_max", "convention"),
    ("tools/formel", "convention"),
])
def test_chaque_regle_porte_sa_raison(dossier, mot):
    """Une règle d'ignore sans sa raison se fait retirer par le prochain qui
    trouve le dossier absent du dépôt et croit à un oubli.

    Les deux raisons sont **différentes**, et c'est le point : l'une est une
    contrainte de droit, l'autre un choix. Les confondre ferait croire qu'un
    moteur MIT peut entrer dès qu'on est pressé.
    """
    gitignore = (RACINE / ".gitignore").read_text(encoding="utf-8")
    bloc = gitignore.split(dossier + "/")[0][-1200:].lower()

    assert mot in bloc, f"la regle de {dossier} ne dit pas pourquoi elle existe"
