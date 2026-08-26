"""Prépare la purge des secrets présents dans l'historique Git.

Ce script **ne modifie rien**. Il lit l'historique, trouve les valeurs de secrets
qui y ont été écrites en clair, et produit le fichier de remplacement attendu par
`git filter-repo --replace-text`.

Le fichier produit est écrit **en dehors du dépôt**, pour qu'il ne puisse pas
être versionné par accident : il contient les secrets en clair.

    python scripts/preparer_purge_secrets.py

Voir la marche à suivre complète dans `documents/RUNBOOK_PURGE_SECRETS.md`.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Emplacements connus où un secret a été écrit en clair, et le motif qui l'isole.
# Chaque entrée : (fichier suivi, expression régulière avec un groupe capturant).
EMPLACEMENTS = [
    ("librechat.yaml", re.compile(r'apiKey:\s*"([^"]+)"')),
    (
        "docker-compose.yml",
        re.compile(
            r"^\s*-\s*(?:CREDS_KEY|JWT_SECRET|JWT_REFRESH_SECRET"
            r"|WEBUI_SECRET_KEY|OPENAI_API_KEY|ARENA_API_KEY)=(.+)$",
            re.MULTILINE,
        ),
    ),
]

# Une valeur qui commence par ${ est une référence à une variable, pas un secret.
MOTIF_REFERENCE = re.compile(r"^\$\{.*\}$")

# Valeurs trop courtes ou manifestement non secrètes.
LONGUEUR_MINIMALE = 8


def est_un_secret(valeur: str) -> bool:
    """Distingue une vraie valeur d'une référence à une variable d'environnement."""
    valeur = valeur.strip().strip('"').strip("'")
    if not valeur or len(valeur) < LONGUEUR_MINIMALE:
        return False
    return not MOTIF_REFERENCE.match(valeur)


def masquer(valeur: str) -> str:
    """Affiche une valeur sans la révéler.

    `exemple-cle-2099` devient `exem…2099 (16 car.)`. L'exemple est inventé :
    écrire une valeur réelle ici ferait de ce fichier une fuite de plus.
    """
    if len(valeur) <= 8:
        return "…" * len(valeur)
    return f"{valeur[:4]}…{valeur[-4:]} ({len(valeur)} car.)"


def commandes_git(*arguments: str, depot: Path = RACINE) -> str:
    """Exécute une commande git dans `depot` et renvoie sa sortie.

    Le décodage est tolérant : d'anciennes versions de `docker-compose.yml` sont
    encodées en latin-1, et un décodage UTF-8 strict fait échouer la lecture de
    l'historique. Les valeurs recherchées sont en ASCII, un caractère de
    remplacement ailleurs est sans conséquence.

    `depot` est un paramètre pour que la fonction soit testable sur un dépôt
    fabriqué pour l'occasion, plutôt que sur celui-ci — dont le contenu change.
    """
    resultat = subprocess.run(
        ["git", *arguments], cwd=depot, capture_output=True, check=False
    )
    if resultat.returncode != 0:
        return ""
    return resultat.stdout.decode("utf-8", errors="replace")


def historique_complet(depot: Path = RACINE) -> bool:
    """Faux si le dépôt est un clone superficiel : l'historique y est tronqué.

    Un `git clone --depth 1` — ce que fait `actions/checkout` par défaut — ne
    montre qu'un commit. Chercher des secrets dedans ne prouve rien.
    """
    return not (Path(depot) / ".git" / "shallow").exists()


def secrets_de_l_historique(depot: Path = RACINE) -> dict[str, str]:
    """Renvoie {valeur en clair: fichier où elle a été trouvée}."""
    trouves: dict[str, str] = {}
    for fichier, motif in EMPLACEMENTS:
        commits = commandes_git("log", "--all", "--format=%H", "--", fichier, depot=depot).split()
        for commit in commits:
            contenu = commandes_git("show", f"{commit}:{fichier}", depot=depot)
            for valeur in motif.findall(contenu):
                valeur = valeur.strip().strip('"').strip("'")
                if est_un_secret(valeur):
                    trouves.setdefault(valeur, fichier)
    return trouves


def principal() -> int:
    if not (RACINE / ".git").exists():
        print("Erreur : ce script doit tourner dans le dépôt Git d'ARENA.")
        return 1

    if not historique_complet():
        print("Ce depot est un clone superficiel : l'historique est tronque.")
        print("Recupere-le en entier avant de purger :  git fetch --unshallow")
        return 1

    trouves = secrets_de_l_historique()
    if not trouves:
        print("Aucun secret en clair trouvé dans l'historique. Rien à purger.")
        return 0

    destination = RACINE.parent / "arena-secrets-a-purger.txt"
    lignes = [f"{valeur}==>SECRET_PURGE_{i}" for i, valeur in enumerate(sorted(trouves), 1)]
    destination.write_text("\n".join(lignes) + "\n", encoding="utf-8")

    print(f"{len(trouves)} secret(s) trouvé(s) dans l'historique :\n")
    for i, valeur in enumerate(sorted(trouves), 1):
        print(f"  {i}. {masquer(valeur):28} vu dans {trouves[valeur]}")

    print(f"\nFichier de remplacement écrit ici :\n  {destination}")
    print("\nIl est hors du dépôt, et il contient les secrets en clair.")
    print("À supprimer une fois la purge terminée.")
    print("\nÉtape suivante : documents/RUNBOOK_PURGE_SECRETS.md, étape 4.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
