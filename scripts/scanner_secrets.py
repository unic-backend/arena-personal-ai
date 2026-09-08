"""Attrape un secret AVANT qu'il entre — dans l'arbre de travail, pas l'historique.

    python scripts/scanner_secrets.py

`preparer_purge_secrets.py` est son frère, et ils ne font pas la même chose :
celui-là nettoie les **six secrets déjà connus** de l'historique, à des
emplacements codés en dur (`librechat.yaml`, `docker-compose.yml`). Ce script-ci
regarde ce qui est **suivi maintenant**, n'importe où, et refuse qu'un *nouveau*
secret — une clé collée dans un fichier, un `.env` versionné par accident, une
clé privée oubliée — franchisse le prochain commit. Les deux ensemble, parce
qu'aucun ne suffit : purger l'historique ne surveille pas le fichier que
j'écrirai demain.

Deux règles, pour que ce ne soit ni du bruit ni un mensonge :

1. **On ne scanne que les fichiers suivis par Git.** Un secret dans
   `node_modules/`, `.venv/` ou un cache n'entre pas dans un commit — le
   signaler noierait le vrai problème. `git ls-files` dit exactement ce qui est
   suivi.

2. **Haute confiance seulement.** Une clé privée PEM, une clé AWS/Google/Slack/
   GitHub reconnaissable à son préfixe, ou une affectation `api_key = "..."`
   dont la valeur a vraiment une tête de secret. Une référence `${VAR}`, un
   exemple (`exemple`, `changeme`, `your-key`…) ou une valeur trop courte ne
   sont pas des secrets. Un scanner qui crie à chaque chaîne longue finit
   ignoré, et c'est pire que pas de scanner.

Sortie non nulle dès qu'il trouve quelque chose : utilisable tel quel comme
garde avant un commit ou dans une CI. La valeur trouvée est **masquée** — la
révéler ferait de la sortie du scanner une fuite de plus.
"""
from __future__ import annotations

import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

RACINE = Path(__file__).resolve().parent.parent

#: Une ligne qui porte ce marqueur est sautée. Pour un cas légitime et rare —
#: une valeur d'exemple d'une forme que la liste des placeholders n'attrape pas.
#: Explicite, visible dans la revue : personne ne l'écrit sans savoir pourquoi.
MARQUEUR_IGNORER = "scanner-secrets: ignore"

#: Une valeur qui commence par ${ (ou $()) est une référence, pas un secret.
MOTIF_REFERENCE = re.compile(r"^\$[\{(]")

#: Ce qui trahit une valeur d'exemple plutôt qu'un vrai secret. Comparé en
#: minuscules, sous-chaîne : `VOTRE-CLE-ICI` comme `your_api_key_here` tombent.
PLACEHOLDERS = (
    "exemple", "example", "changeme", "change-me", "your-", "your_", "votre-",
    "votre_", "placeholder", "dummy", "fake", "factice", "redacted", "xxxxxxx",
    "...", "<", "test-cle", "cle-de-test", "sample", "specimen", "0123456789abcdef",
)

LONGUEUR_MINIMALE = 12

#: Secrets reconnaissables à leur forme, indépendamment du contexte. Chaque
#: motif est assez spécifique pour qu'une correspondance soit quasi certaine.
MOTIFS_NOMMES = [
    ("clé privée PEM", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("clé d'accès AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("clé API Google", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("jeton Slack", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("jeton GitHub", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36}\b")),
    ("jeton GitHub (fin)", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b")),
    ("clé Stripe secrète", re.compile(r"\bsk_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("jeton OpenAI", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
]

#: Une affectation dont le NOM annonce un secret. Le nom fait la moitié du
#: travail : `chemin = "..."` n'est pas suspect, `api_key = "..."` l'est.
MOTIF_AFFECTATION = re.compile(
    r"""(?ix)
    \b(
        (?:api[_-]?key) | secret(?:[_-]?key)? | (?:access|auth|bearer)[_-]?token |
        password | passwd | (?:private|priv)[_-]?key | client[_-]?secret |
        (?:api[_-]?)?token
    )
    \b \s* [:=] \s*
    ['"]([^'"]{8,})['"]
    """,
)


def entropie_de_shannon(valeur: str) -> float:
    """Bits d'information par caractère. `aaaaaaaa` est bas, une vraie clé haut.

    Sert à écarter les faux positifs de la règle d'affectation : `password =
    "password"` ou `token = "1111111111"` ont un nom suspect mais une valeur qui
    n'a rien de secret.
    """
    if not valeur:
        return 0.0
    frequences = {c: valeur.count(c) for c in set(valeur)}
    n = len(valeur)
    return -sum((f / n) * math.log2(f / n) for f in frequences.values())


def est_un_placeholder(valeur: str) -> bool:
    bas = valeur.lower()
    return any(marque in bas for marque in PLACEHOLDERS)


def est_une_valeur_secrete(valeur: str) -> bool:
    """Une valeur d'affectation a-t-elle vraiment une tête de secret ?

    Vrai seulement si elle est assez longue, n'est pas une référence `${VAR}`,
    n'est pas un exemple, et porte assez de désordre (entropie) pour ne pas être
    un mot de passe factice comme `changeme`.
    """
    valeur = valeur.strip()
    if len(valeur) < LONGUEUR_MINIMALE:
        return False
    if MOTIF_REFERENCE.match(valeur):
        return False
    if est_un_placeholder(valeur):
        return False
    # Un vrai secret mélange les caractères. Le seuil est bas exprès : il ne sert
    # qu'à écarter les valeurs répétitives, pas à juger la force d'une clé.
    return entropie_de_shannon(valeur) >= 3.0


def masquer(valeur: str) -> str:
    """Montre qu'on a trouvé quelque chose sans le révéler.

    `exemple-cle-2099-abcd` devient `exem…abcd (21 car.)`. Une valeur courte est
    entièrement masquée : en montrer les bords en révélerait trop.
    """
    valeur = valeur.strip()
    if len(valeur) <= 8:
        return "…" * len(valeur)
    return f"{valeur[:4]}…{valeur[-4:]} ({len(valeur)} car.)"


@dataclass(frozen=True)
class Trouvaille:
    """Un secret probable, situé assez précisément pour aller le corriger."""

    fichier: str
    ligne: int
    genre: str
    masque: str

    def rendre(self) -> str:
        return f"  {self.fichier}:{self.ligne}  [{self.genre}]  {self.masque}"


def scanner_le_texte(fichier: str, texte: str) -> List[Trouvaille]:
    """Le cœur, pur et testable : ce qu'un contenu de fichier révèle.

    Séparé de toute lecture disque ou appel Git pour être éprouvé sur des
    contenus fabriqués, plutôt que sur ce dépôt — dont le contenu change.
    """
    trouvailles: List[Trouvaille] = []
    for numero, ligne in enumerate(texte.splitlines(), 1):
        if MARQUEUR_IGNORER in ligne:
            continue

        for genre, motif in MOTIFS_NOMMES:
            trouve = motif.search(ligne)
            if trouve:
                trouvailles.append(Trouvaille(fichier, numero, genre, masquer(trouve.group(0))))

        for nom, valeur in MOTIF_AFFECTATION.findall(ligne):
            if est_une_valeur_secrete(valeur):
                trouvailles.append(
                    Trouvaille(fichier, numero, f"affectation {nom.lower()}", masquer(valeur)))
    return trouvailles


def _est_binaire(donnees: bytes) -> bool:
    """Un octet nul ne se trouve pas dans du texte : c'est un fichier binaire."""
    return b"\x00" in donnees


def fichiers_suivis(depot: Path = RACINE) -> Optional[List[str]]:
    """Les chemins suivis par Git, ou None si `depot` n'est pas un dépôt.

    None, pas `[]` : « pas un dépôt » et « un dépôt vide » ne se répondent pas
    pareil. Le premier est une erreur d'usage, le second un fait sur le contenu.
    """
    resultat = subprocess.run(
        ["git", "ls-files", "-z"], cwd=depot, capture_output=True, check=False)
    if resultat.returncode != 0:
        return None
    noms = resultat.stdout.decode("utf-8", errors="replace").split("\0")
    return [n for n in noms if n]


def scanner_le_depot(depot: Path = RACINE,
                     chemins: Optional[Iterable[str]] = None) -> List[Trouvaille]:
    """Scanne les fichiers suivis (ou la liste `chemins` donnée, pour un test)."""
    if chemins is None:
        suivis = fichiers_suivis(depot)
        chemins = suivis if suivis is not None else []

    trouvailles: List[Trouvaille] = []
    for relatif in chemins:
        chemin = depot / relatif
        try:
            donnees = chemin.read_bytes()
        except (OSError, FileNotFoundError):
            continue
        if _est_binaire(donnees):
            continue
        texte = donnees.decode("utf-8", errors="replace")
        trouvailles.extend(scanner_le_texte(relatif, texte))
    return trouvailles


def principal(depot: Path = RACINE) -> int:
    if fichiers_suivis(depot) is None:
        print("Erreur : ce script doit tourner dans un dépôt Git.")
        return 2

    trouvailles = scanner_le_depot(depot)
    if not trouvailles:
        print("Aucun secret probable dans les fichiers suivis. Rien n'entre.")
        return 0

    print(f"{len(trouvailles)} secret(s) probable(s) — À VÉRIFIER avant tout commit :\n")
    for t in trouvailles:
        print(t.rendre())
    print(
        "\nSi c'en est un : retire-le du fichier, mets-le dans une variable"
        "\nd'environnement, et change-le (il a pu être vu). Si c'est un faux"
        f"\npositif légitime, ajoute en fin de ligne :  # {MARQUEUR_IGNORER}")
    return 1


if __name__ == "__main__":
    sys.exit(principal())
