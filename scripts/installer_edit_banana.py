"""Installation explicite et reproductible du moteur Edit-Banana externe.

Edit-Banana (BIT-DataLab/Edit-Banana) permet de convertir une image de schéma
ou diagramme statique en document DrawIO éditable (.drawio / XML).

Ce script installe Edit-Banana dans un dossier EXTERNE à ARENA, avec son propre
environnement Python (.venv), sans jamais modifier l'environnement principal d'ARENA.

Licences & Accès :
- Edit-Banana : GNU AGPL-3.0 (fichier LICENSE officiel)
- SAM3 (Segment Anything Model 3) : licence Meta / SAM3, accès au checkpoint
  soumis aux conditions officielles (Hugging Face / ModelScope).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import venv
from pathlib import Path

UPSTREAM = "https://github.com/BIT-DataLab/Edit-Banana.git"
COMMIT = "88c6e288ef8329606114eb91924559c5d1838d2e"


def executer(*commande: str, cwd: Path | None = None) -> None:
    subprocess.run(commande, cwd=cwd, check=True)


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("destination", type=Path, help="Dossier externe où installer Edit-Banana")
    analyseur.add_argument(
        "--accept-agpl-license",
        action="store_true",
        help="Confirme la lecture de la licence GNU AGPL-3.0 d'Edit-Banana et des conditions d'accès de SAM3",
    )
    analyseur.add_argument(
        "--sam3-checkpoint",
        type=Path,
        default=None,
        help="Chemin vers un checkpoint SAM3 (sam3.pt) déjà téléchargé",
    )
    args = analyseur.parse_args()

    if not args.accept_agpl_license:
        analyseur.error(
            "Lire le fichier LICENSE (GNU AGPL-3.0) de https://github.com/BIT-DataLab/Edit-Banana "
            "ainsi que les conditions d'accès aux poids SAM3, puis passer --accept-agpl-license."
        )

    destination = args.destination.expanduser().resolve()
    depot_arena = Path(__file__).resolve().parents[1]
    if destination == depot_arena or depot_arena in destination.parents:
        raise RuntimeError("Edit-Banana et ses dépendances doivent être installés hors du dépôt ARENA.")

    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"[CLONE] Clonage de {UPSTREAM} vers {destination}...")
        executer("git", "clone", UPSTREAM, str(destination))

    if not (destination / ".git").is_dir():
        raise RuntimeError(f"La destination {destination} existe mais n'est pas un checkout Git d'Edit-Banana.")

    origine = subprocess.check_output(
        ["git", "-C", str(destination), "remote", "get-url", "origin"], text=True
    ).strip()
    if "BIT-DataLab/Edit-Banana" not in origine:
        raise RuntimeError(f"Origine inattendue pour le dépôt : {origine}")

    try:
        executer("git", "fetch", "origin", COMMIT, cwd=destination)
        executer("git", "checkout", "--detach", COMMIT, cwd=destination)
    except subprocess.CalledProcessError:
        print("[INFO] Révision spécifique non récupérée par fetch direct, utilisation de HEAD.")

    # Vérification des fichiers amont attendus
    fichiers_requis = ["main.py", "requirements.txt"]
    for nom in fichiers_requis:
        if not (destination / nom).is_file():
            raise RuntimeError(f"Fichier requis manquant dans le checkout Edit-Banana : {nom}")

    # Préparation des dossiers locaux d'Edit-Banana
    (destination / "input").mkdir(exist_ok=True)
    (destination / "output").mkdir(exist_ok=True)
    (destination / "models").mkdir(exist_ok=True)

    # Configuration par défaut
    config_exemple = destination / "config" / "config.yaml.example"
    config_active = destination / "config" / "config.yaml"
    if config_exemple.is_file() and not config_active.is_file():
        import shutil
        shutil.copyfile(config_exemple, config_active)
        print("[CONFIG] config/config.yaml initialisé à partir de config.yaml.example.")

    # Création de l'environnement Python virtuel isolé
    environnement = destination / ".venv"
    if not environnement.exists():
        print(f"[VENV] Création de l'environnement virtuel dans {environnement}...")
        venv.EnvBuilder(with_pip=True).create(environnement)

    python = environnement / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    print("[PIP] Mise à niveau de pip...")
    executer(str(python), "-m", "pip", "install", "--upgrade", "pip")

    print("[PIP] Installation des dépendances d'Edit-Banana (PyTorch, OCR, etc.)...")
    executer(str(python), "-m", "pip", "install", "-r", str(destination / "requirements.txt"))

    # Vérification du checkpoint SAM3
    if args.sam3_checkpoint:
        ckpt = args.sam3_checkpoint.expanduser().resolve()
        if not ckpt.is_file():
            print(f"[AVERTISSEMENT] Le checkpoint spécifié n'existe pas : {ckpt}")
        else:
            destination_ckpt = destination / "models" / "sam3.pt"
            if not destination_ckpt.exists():
                import shutil
                shutil.copyfile(ckpt, destination_ckpt)
                print(f"[SAM3] Checkpoint copié vers {destination_ckpt}")

    sam3_present = (destination / "models" / "sam3.pt").is_file() or (
        destination / "models" / "sam3_ms" / "sam3.pt"
    ).is_file()

    print("\n" + "=" * 60)
    print("  Installation d'Edit-Banana terminée avec succès !")
    print("=" * 60)
    if not sam3_present:
        print("\n[ATTENTION] Checkpoint SAM3 non détecté.")
        print("Pour finaliser la configuration, téléchargez le modèle sam3.pt")
        print("depuis Hugging Face ou ModelScope selon les conditions de licence SAM3,")
        print(f"et placez-le dans : {destination / 'models' / 'sam3.pt'}")
    print("\nAjoutez les variables suivantes à votre fichier .env dans ARENA :")
    print(f"USMAN_EDIT_BANANA_ROOT={destination}")
    print(f"USMAN_EDIT_BANANA_PYTHON={python}")
    print("USMAN_EDIT_BANANA_LICENSE_ACCEPTED=true")
    if sam3_present:
        print(f"USMAN_EDIT_BANANA_SAM3_CHECKPOINT={destination / 'models' / 'sam3.pt'}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
