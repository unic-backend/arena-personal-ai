"""Le moteur Xaar Kaname reste hors du dépôt. C'est juridique avant d'être technique.

**Xaar Kaname** est le nom ARENA de la capacité portée par **Deep-Live-Cam**,
qui est sous **AGPL-3.0**. `LICENSE` d'ARENA dit « All rights reserved », et le
dépôt est **public** (DEC-0039). Faire entrer le source de Deep-Live-Cam ici
ferait d'ARENA une œuvre dérivée : ARENA devrait alors être publié sous AGPL.

C'est exactement le raisonnement déjà tenu pour **VoiceStudio** (DEC-0027) et
inscrit en tête de `core/connectors/audio_voix.py` : la frontière est un
**processus séparé**, joint par HTTP ou par sa ligne de commande. L'AGPL
n'étend pas ses obligations à un programme qui se contente d'appeler un
service.

`test_la_regle_du_depot_vaut_pour_tous_les_moteurs_externes` est celui qui
compte : il ne fait pas confiance à une intention écrite, il **mesure** que
VoiceStudio, WanGP et MoneyPrinterTurbo n'ont jamais mis une ligne dans git —
et exige la même chose de Xaar.

Trois problèmes sont réglés par la même règle, et le premier est le plus
grave : la licence, puis `models/inswapper_128.onnx` (plusieurs centaines de
Mo), puis `.venv/` avec ses DLL CUDA/cuDNN et les images produites.
"""
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

#: Le dossier où le moteur externe est installé, à côté d'ARENA.
DOSSIER_MOTEUR = "tools/video/xaar_kaname"

#: Ce qu'un clone de Deep-Live-Cam pose sur le disque, et qui ne doit jamais
#: entrer : l'environnement CUDA, le modèle, le source AGPL, les rendus.
CE_QUI_NE_DOIT_PAS_ENTRER = (
    "Deep-Live-Cam/.venv/Lib/site-packages/onnxruntime/capi/cudnn64_9.dll",
    "Deep-Live-Cam/models/inswapper_128.onnx",
    "Deep-Live-Cam/run.py",
    "Deep-Live-Cam/modules/core.py",
    "Deep-Live-Cam/arena_xaar_final.jpg",
    "Deep-Live-Cam/output.mp4",
)


def _est_ignore(chemin: str) -> bool:
    """Git ignorerait-il ce chemin ? La question est posée à git, pas déduite."""
    return subprocess.run(
        ["git", "check-ignore", "-q", chemin],
        cwd=RACINE, capture_output=True, check=False,
    ).returncode == 0


@pytest.mark.parametrize("relatif", CE_QUI_NE_DOIT_PAS_ENTRER)
def test_rien_du_moteur_externe_ne_peut_entrer_dans_le_depot(relatif):
    assert _est_ignore(f"{DOSSIER_MOTEUR}/{relatif}"), (
        f"{relatif} entrerait dans un depot PUBLIC : source AGPL, modele lourd "
        "ou rendu. La regle `tools/video/xaar_kaname/` a saute du .gitignore.")


def test_le_dossier_du_moteur_est_ignore_en_entier():
    """Une règle par extension oublierait toujours le fichier suivant."""
    assert _est_ignore(f"{DOSSIER_MOTEUR}/un_fichier_qu_on_n_a_pas_prevu.bin")


def test_aucun_fichier_du_moteur_n_est_deja_suivi():
    """Le contrôle qui compte : rien de Deep-Live-Cam n'est versionné.

    Une règle d'ignore n'a aucun effet sur un fichier déjà suivi — si l'un
    était entré avant la règle, il y resterait sans que rien ne le dise.
    """
    suivis = subprocess.run(
        ["git", "ls-files", DOSSIER_MOTEUR],
        cwd=RACINE, capture_output=True, text=True, check=False,
    ).stdout.split()

    assert suivis == [], f"du moteur externe est deja dans git : {suivis}"


def test_la_regle_du_depot_vaut_pour_tous_les_moteurs_externes():
    """VoiceStudio, WanGP, MoneyPrinterTurbo : aucun n'a jamais mis une ligne
    dans git. Xaar suit la même règle, et ce test la mesure au lieu de la
    croire sur parole.

    Ce que le dépôt porte pour chacun : le connecteur, ses tests, un script
    d'installation. Jamais le moteur.
    """
    suivis = subprocess.run(
        ["git", "ls-files"], cwd=RACINE, capture_output=True, text=True, check=False,
    ).stdout.splitlines()

    for moteur in ("Deep-Live-Cam", "VoiceStudio", "WanGP", "MoneyPrinterTurbo"):
        dedans = [f for f in suivis if moteur.lower() in f.lower()
                  and not f.startswith(("docs/", "scripts/installer_",
                                        "core/connectors/", "tests/"))]
        assert dedans == [], f"du source de {moteur} est versionne : {dedans}"


def test_la_raison_juridique_est_ecrite_a_cote_de_la_regle():
    """Une règle d'ignore sans sa raison se fait retirer par le prochain qui
    trouve le dossier absent du dépôt et croit à un oubli."""
    gitignore = (RACINE / ".gitignore").read_text(encoding="utf-8")

    bloc = gitignore.split(DOSSIER_MOTEUR)[0][-1400:]
    assert "AGPL" in bloc, "la regle ne dit pas pourquoi elle existe"
    assert "VoiceStudio" in bloc, "la regle ne cite pas le precedent du depot"
