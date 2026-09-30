"""Installation explicite et reproductible du moteur CodeFormer externe.

Aucun appel de ce script n'a lieu au demarrage d'ARENA. Les poids restent dans
le checkout externe choisi par l'operateur et sont controles par SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import urllib.request
import venv
from dataclasses import dataclass
from pathlib import Path

COMMIT = "b33cc7d639d6545bfcccc7e0bc6ae51f24e79c2b"
UPSTREAM = "https://github.com/sczhou/CodeFormer.git"
RELEASE = "https://github.com/sczhou/CodeFormer/releases/download/v0.1.0"


@dataclass(frozen=True)
class Poids:
    nom: str
    dossier: str
    sha256: str


POIDS_REQUIS = (
    Poids("codeformer.pth", "CodeFormer", "1009e537e0c2a07d4cabce6355f53cb66767cd4b4297ec7a4a64ca4b8a5684b7"),
    Poids("detection_Resnet50_Final.pth", "facelib", "6d1de9c2944f2ccddca5f5e010ea5ae64a39845a86311af6fdf30841b0a5a16d"),
    Poids("parsing_parsenet.pth", "facelib", "3d558d8d0e42c20224f13cf5a29c79eba2d59913419f945545d8cf7b72920de2"),
)
POIDS_FOND = Poids(
    "RealESRGAN_x2plus.pth", "realesrgan",
    "49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb",
)


def empreinte(chemin: Path) -> str:
    hacheur = hashlib.sha256()
    with chemin.open("rb") as fichier:
        for bloc in iter(lambda: fichier.read(1024 * 1024), b""):
            hacheur.update(bloc)
    return hacheur.hexdigest()


def telecharger(poids: Poids, racine: Path) -> None:
    destination = racine / "weights" / poids.dossier / poids.nom
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and empreinte(destination) == poids.sha256:
        print(f"[OK] {poids.nom} deja present et verifie")
        return
    if destination.exists():
        raise RuntimeError(f"Poids existant avec une empreinte incorrecte : {destination}")
    partiel = destination.with_suffix(destination.suffix + ".part")
    partiel.unlink(missing_ok=True)
    print(f"[DOWNLOAD] {poids.nom}")
    try:
        urllib.request.urlretrieve(f"{RELEASE}/{poids.nom}", partiel)
        mesure = empreinte(partiel)
        if mesure != poids.sha256:
            raise RuntimeError(f"SHA-256 incorrect pour {poids.nom}: {mesure}")
        partiel.replace(destination)
    finally:
        partiel.unlink(missing_ok=True)


def executer(*commande: str, cwd: Path | None = None) -> None:
    subprocess.run(commande, cwd=cwd, check=True)


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("destination", type=Path, help="dossier externe ou installer CodeFormer")
    analyseur.add_argument("--with-background", action="store_true", help="ajoute le poids Real-ESRGAN")
    analyseur.add_argument(
        "--accept-noncommercial-license", action="store_true",
        help="confirme la lecture de NTU S-Lab License 1.0 (usage commercial soumis a autorisation)",
    )
    args = analyseur.parse_args()
    if not args.accept_noncommercial_license:
        analyseur.error(
            "Lire https://github.com/sczhou/CodeFormer/blob/master/LICENSE puis passer "
            "--accept-noncommercial-license. Pour un usage commercial, obtenir d'abord l'autorisation des contributeurs."
        )

    destination = args.destination.expanduser().resolve()
    depot_arena = Path(__file__).resolve().parents[1]
    if destination == depot_arena or depot_arena in destination.parents:
        raise RuntimeError("CodeFormer et ses poids doivent etre installes hors du depot ARENA.")
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        executer("git", "clone", UPSTREAM, str(destination))
    if not (destination / ".git").is_dir():
        raise RuntimeError("La destination existe mais n'est pas un checkout Git de CodeFormer.")
    origine = subprocess.check_output(
        ["git", "-C", str(destination), "remote", "get-url", "origin"], text=True).strip()
    if origine.rstrip("/").removesuffix(".git") != UPSTREAM.removesuffix(".git"):
        raise RuntimeError(f"Origine inattendue : {origine}")
    executer("git", "fetch", "origin", COMMIT, cwd=destination)
    executer("git", "checkout", "--detach", COMMIT, cwd=destination)

    environnement = destination / ".venv"
    if not environnement.exists():
        venv.EnvBuilder(with_pip=True).create(environnement)
    python = environnement / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    executer(str(python), "-m", "pip", "install", "--upgrade", "pip")
    executer(str(python), "-m", "pip", "install", "-r", str(destination / "requirements.txt"))
    # L'amont demande explicitement cette installation editable pour enregistrer
    # les architectures BasicSR qu'utilise son script d'inference.
    executer(str(python), "setup.py", "develop", cwd=destination / "basicsr")

    for poids in (*POIDS_REQUIS, *((POIDS_FOND,) if args.with_background else ())):
        telecharger(poids, destination)

    print("\nInstallation verifiee. Ajouter dans .env :")
    print(f"USMAN_CODEFORMER_ROOT={destination}")
    print(f"USMAN_CODEFORMER_PYTHON={python}")
    print("USMAN_CODEFORMER_LICENSE_ACCEPTED=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
