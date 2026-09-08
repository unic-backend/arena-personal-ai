"""Les dépendances d'Usman ont-elles des failles connues ? Mesuré, pas supposé.

    python scripts/scanner_dependances.py

Enveloppe `pip-audit`, qui compare les versions épinglées à la base d'avis de
vulnérabilités (OSV / PyPI). Ce script n'invente aucune faille : il relaie ce
que pip-audit trouve, avec le paquet, la version, l'identifiant et la version
qui corrige.

**Trois états, jamais deux** — la même discipline que `scripts/doctor.py` :

- `PROPRE`   : pip-audit a répondu, aucune faille connue.
- `FAILLES`  : pip-audit a répondu, voici ce qu'il a trouvé.
- `INCONNU`  : pip-audit n'est pas installé, OU la base d'avis est injoignable
               (le PC d'Usman peut être hors ligne). On le **dit** — on ne
               renvoie surtout pas « aucune faille », qui se lirait comme une
               garantie qu'on n'a pas.

Un `INCONNU` pris pour un `PROPRE` est le mensonge le plus cher ici : il
endort une alerte qui n'a jamais été mesurée. C'est exactement ce que
`resultat.py` interdit ailleurs — un SUCCESS sans preuve.

La cible par défaut est `requirements.txt` (les dépendances directes qu'Usman
maintient). `requirements.lock.txt` épingle aussi le transitif : à passer en
argument pour un audit complet.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

RACINE = Path(__file__).resolve().parent.parent

#: Renvoie le JSON de pip-audit pour un fichier, ou None si la mesure a échoué.
#: Type nommé pour que les tests injectent un faux exécuteur sans réseau.
Executeur = Callable[[Path], Optional[str]]


@dataclass(frozen=True)
class Faille:
    """Une vulnérabilité connue touchant une version épinglée."""

    paquet: str
    version: str
    identifiant: str
    corrige_dans: str          # les versions qui corrigent, ou "aucune connue"
    resume: str

    def rendre(self) -> str:
        vers = f" → corrigé dans {self.corrige_dans}" if self.corrige_dans else ""
        return f"  {self.paquet} {self.version}  [{self.identifiant}]{vers}"


@dataclass(frozen=True)
class Rapport:
    """Le résultat d'un audit : un état franc, et ce qui va avec."""

    etat: str                  # "PROPRE" | "FAILLES" | "INCONNU"
    failles: List[Faille]
    raison: str = ""           # pourquoi INCONNU — vide sinon

    @property
    def code_de_sortie(self) -> int:
        # 0 propre, 1 des failles à corriger, 2 mesure impossible. Un CI peut
        # traiter 2 différemment de 1 : « je n'ai pas pu vérifier » n'est pas
        # « c'est cassé ».
        return {"PROPRE": 0, "FAILLES": 1, "INCONNU": 2}[self.etat]


def _resumer(description: str) -> str:
    """Une ligne lisible tirée d'une description parfois longue et en Markdown."""
    texte = " ".join((description or "").split())
    texte = texte.lstrip("# ").strip()
    return texte[:140] + "…" if len(texte) > 140 else texte


def analyser_rapport(json_texte: str) -> List[Faille]:
    """Extrait les failles du JSON de pip-audit. Lève ValueError si illisible.

    Pur : aucune lecture disque, aucun réseau. C'est ici que se teste la
    lecture d'un rapport, sur un JSON fabriqué plutôt que sur une vraie
    interrogation du réseau — qui change chaque jour.
    """
    try:
        donnees = json.loads(json_texte)
    except (json.JSONDecodeError, TypeError) as erreur:
        raise ValueError(f"sortie pip-audit illisible : {erreur}") from erreur

    if not isinstance(donnees, dict) or "dependencies" not in donnees:
        raise ValueError("sortie pip-audit sans champ 'dependencies'")

    failles: List[Faille] = []
    # pip-audit peut lister deux fois la même faille (deux chemins de
    # résolution vers le même paquet). Le même (paquet, version, id) n'apporte
    # rien la seconde fois : on le garde une fois, sans rien cacher d'autre.
    deja_vues = set()
    for paquet in donnees.get("dependencies", []):
        if not isinstance(paquet, dict):
            continue
        nom = str(paquet.get("name", "?"))
        version = str(paquet.get("version", "?"))
        for vuln in paquet.get("vulns", []) or []:
            identifiant = str(vuln.get("id", "?"))
            cle = (nom, version, identifiant)
            if cle in deja_vues:
                continue
            deja_vues.add(cle)
            corrections = vuln.get("fix_versions") or []
            failles.append(Faille(
                paquet=nom,
                version=version,
                identifiant=identifiant,
                corrige_dans=", ".join(str(v) for v in corrections),
                resume=_resumer(vuln.get("description", "")),
            ))
    return failles


def _executeur_reel(fichier: Path) -> Optional[str]:
    """Lance le vrai pip-audit. Renvoie None si l'outil manque ou échoue.

    None couvre les deux cas d'INCONNU : binaire absent, et réseau/base
    injoignable (pip-audit sort alors non nul). On ne distingue pas ici la
    cause — `auditer` la nomme à partir de ce qui est disponible.
    """
    if shutil.which("pip-audit") is None:
        return None
    try:
        acheve = subprocess.run(
            ["pip-audit", "-r", str(fichier), "-f", "json", "--progress-spinner", "off"],
            capture_output=True, text=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    # pip-audit sort en 1 quand il TROUVE des failles : ce n'est pas un échec,
    # le JSON est sur stdout. Il n'échoue vraiment que sans stdout exploitable.
    return acheve.stdout or None


def auditer(fichier: Path = RACINE / "requirements.txt",
            executeur: Executeur = _executeur_reel) -> Rapport:
    """Audit d'un fichier de dépendances, avec un état franc en toutes circonstances."""
    if not fichier.exists():
        return Rapport("INCONNU", [], f"fichier introuvable : {fichier}")

    if shutil.which("pip-audit") is None and executeur is _executeur_reel:
        return Rapport("INCONNU", [],
                       "pip-audit n'est pas installé (pip install pip-audit)")

    sortie = executeur(fichier)
    if sortie is None:
        return Rapport("INCONNU", [],
                       "pip-audit n'a pas répondu — outil absent ou base d'avis injoignable")

    try:
        failles = analyser_rapport(sortie)
    except ValueError as erreur:
        return Rapport("INCONNU", [], str(erreur))

    return Rapport("FAILLES" if failles else "PROPRE", failles)


def principal(fichier: Optional[Path] = None) -> int:
    cible = fichier or (RACINE / "requirements.txt")
    rapport = auditer(cible)

    if rapport.etat == "INCONNU":
        print(f"INCONNU — {rapport.raison}")
        print("La mesure n'a pas pu se faire. Ce n'est pas « aucune faille ».")
        return rapport.code_de_sortie

    if rapport.etat == "PROPRE":
        print(f"PROPRE — aucune faille connue dans {cible.name}.")
        return rapport.code_de_sortie

    print(f"{len(rapport.failles)} faille(s) connue(s) dans {cible.name} :\n")
    for f in rapport.failles:
        print(f.rendre())
    print("\nCorrige en montant les versions indiquées dans le fichier, puis"
          "\nrelance la suite de tests avant de fusionner.")
    return rapport.code_de_sortie


if __name__ == "__main__":
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(principal(arg))
