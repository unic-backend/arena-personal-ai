"""Détection déterministe de la pile technique d'un projet.

Mission ARENA × AUTOSKILLS (10/09/2026). Étudier `midudev/autoskills` (commit
`0ec7253`, **CC-BY-NC-4.0** — vérifié dans le `package.json` du paquet
`autoskills` lui-même, pas seulement le `LICENSE` racine du site vitrine) et
donner à Dioumtoukay la capacité de savoir QUELLES technologies sont
présentes dans un projet, sans jamais appeler de modèle pour le savoir.

**Rien de ce fichier ne vient d'AutoSkills.** Sa licence non-commerciale
interdit toute reprise de code dans un dépôt qui sert une activité
commerciale réelle (UniC Plaquiste, DEC-0002 et suivants). Ce qui est repris
est le PRINCIPE, jamais protégeable en lui-même et déjà appliqué ailleurs
dans ce dépôt (`RepoEngineerTool`, `gitingest`) : une preuve déterministe
plutôt qu'un modèle — présence d'un fichier de config, nom d'un paquet
déclaré, sous-chaîne dans un fichier de config connu. Rapport complet →
`docs/audits/autoskills_audit.md`.

**Détection, jamais estimation.** Une technologie absente rend `False`, pas
`None` : une pile technique n'est ni "peut-être Python" ni "à moitié React".
Une seule lecture par fichier (mise en cache) — un dépôt de plusieurs
centaines de fichiers ne doit pas être relu une fois par technologie
candidate.

**Prise en charge minimale des espaces de travail** : `apps/pwa/` a son
propre `package.json`, distinct de celui de la racine (Python). Un seul
niveau de sous-dossiers directs est sondé pour un `package.json`/
`pyproject.toml` propre — pas la récursion générale de gradle/pnpm-workspace
qu'AutoSkills implémente, dont rien dans ce dépôt n'a besoin aujourd'hui.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("usman.skills.detection")


@dataclass(frozen=True)
class Technologie:
    """Une technologie détectable, et les preuves qui la révèlent.

    Toutes les preuves sont des indices OU : une seule qui matche suffit.
    Un champ vide n'est jamais consulté (jamais de correspondance par
    défaut).
    """

    identifiant: str
    #: Fichiers dont la seule PRÉSENCE (relative à la racine sondée) prouve
    #: la technologie — ex. `("vite.config.ts", "vite.config.js")`.
    fichiers_config: Tuple[str, ...] = ()
    #: Noms de paquets npm (dependencies + devDependencies de `package.json`).
    paquets_npm: Tuple[str, ...] = ()
    #: Sous-chaînes qui, trouvées dans `requirements.txt` (n'importe quelle
    #: ligne, insensible à la casse), prouvent la technologie.
    sous_chaines_requirements: Tuple[str, ...] = ()
    #: (fichier, sous-chaîne) : le fichier doit exister ET la contenir.
    contenu_fichier: Tuple[Tuple[str, str], ...] = ()


#: Le catalogue des technologies qu'ARENA sait reconnaître. Volontairement
#: restreint à ce qui est réellement pertinent ici (la pile d'ARENA lui-même,
#: plus les technologies web/test les plus communes pour « un autre projet »,
#: mission §3/contexte_unifie.py) — pas les ~200 entrées d'AutoSkills, dont
#: la plupart (Terraform, Rails, Swift, Kotlin…) n'ont aucun chemin
#: d'exécution ici et seraient des spécialistes décoratifs (même règle que
#: `core/specialistes/catalogue.py`, règle 1).
TECHNOLOGIES: Tuple[Technologie, ...] = (
    Technologie(identifiant="python",
                fichiers_config=("requirements.txt", "pyproject.toml", "setup.py")),
    Technologie(identifiant="fastapi",
                sous_chaines_requirements=("fastapi",)),
    Technologie(identifiant="typescript",
                fichiers_config=("tsconfig.json",), paquets_npm=("typescript",)),
    Technologie(identifiant="react", paquets_npm=("react", "react-dom")),
    Technologie(identifiant="vite",
                fichiers_config=("vite.config.ts", "vite.config.js", "vite.config.mjs"),
                paquets_npm=("vite",)),
    Technologie(identifiant="tailwindcss",
                fichiers_config=("tailwind.config.ts", "tailwind.config.js"),
                paquets_npm=("tailwindcss", "@tailwindcss/vite")),
    Technologie(identifiant="vitest", paquets_npm=("vitest",)),
    Technologie(identifiant="playwright",
                fichiers_config=("playwright.config.ts", "playwright.config.js"),
                paquets_npm=("playwright", "@playwright/test")),
    Technologie(identifiant="docker", fichiers_config=("Dockerfile", "docker-compose.yml")),
    Technologie(identifiant="github-actions", fichiers_config=(".github/workflows",)),
    Technologie(identifiant="sqlite", sous_chaines_requirements=("aiosqlite",)),
)

#: Combinaisons qui n'existent que si PLUSIEURS technologies coexistent —
#: même idée que `detectCombos` d'AutoSkills (étudiée, jamais copiée) :
#: un projet React seul et un projet React+Vite+TypeScript n'appellent pas
#: la même compétence.
COMBOS: Dict[str, Tuple[str, ...]] = {
    "react-vite-typescript": ("react", "vite", "typescript"),
}


def _lire_json(chemin: Path) -> Optional[Dict[str, object]]:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _paquets_npm(package_json: Optional[Dict[str, object]]) -> set:
    if not package_json:
        return set()
    noms = set()
    for cle in ("dependencies", "devDependencies", "peerDependencies"):
        section = package_json.get(cle)
        if isinstance(section, dict):
            noms.update(section.keys())
    return noms


#: Dossiers jamais descendus, même à la profondeur autorisée — un
#: environnement virtuel ou `node_modules` peut contenir des milliers de
#: `package.json` d'autrui, aucun n'appartient au projet sondé.
_DOSSIERS_IGNORES = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__",
                               "dist", "build", ".next", ".turbo"})


def _enfants_utiles(dossier: Path) -> List[Path]:
    try:
        return sorted(e for e in dossier.iterdir()
                      if e.is_dir() and e.name not in _DOSSIERS_IGNORES
                      and not e.name.startswith("."))
    except OSError:
        return []


#: Ce qui marque un dossier comme un sous-projet à part entière, digne
#: d'être sondé et de mettre fin à la descente (`apps/pwa/` en est le seul
#: exemple réel de ce dépôt) — un manifeste applicatif, PAS le seul
#: `Dockerfile` qu'`apps/backend/` porte seul : lui doit être vu par le
#: passage du dossier lui-même, pas transformé en racine de sous-projet.
def _est_un_sous_projet(dossier: Path) -> bool:
    return (dossier / "package.json").exists() or (dossier / "pyproject.toml").exists()


def _sous_dossiers_a_sonder(racine: Path, profondeur: int = 2) -> List[Path]:
    """Chaque dossier visité jusqu'à `profondeur` (`apps/`, `apps/backend/`,
    `apps/pwa/`…) — pas seulement ceux qui ont un manifeste, pour que
    `Dockerfile` dans `apps/backend/` (aucun `package.json` ni
    `pyproject.toml` à lui) soit vu. Un sous-projet réel
    (`_est_un_sous_projet`) arrête la descente à sa racine — jamais
    `apps/pwa/src/components/...` — parce que rien de plus profond
    n'apporterait de preuve nouvelle. Bornée à `profondeur`, jamais une
    récursion générale sur tout le dépôt (voir la docstring du module)."""
    trouves: List[Path] = []
    niveau = _enfants_utiles(racine)
    for _ in range(profondeur):
        prochain_niveau: List[Path] = []
        for dossier in niveau:
            trouves.append(dossier)
            if not _est_un_sous_projet(dossier):
                prochain_niveau.extend(_enfants_utiles(dossier))
        niveau = prochain_niveau
    return trouves


def _detecter_dans_dossier(dossier: Path) -> set:
    trouvees = set()
    package_json = _lire_json(dossier / "package.json")
    paquets = _paquets_npm(package_json)

    requirements_texte: Optional[str] = None
    chemin_requirements = dossier / "requirements.txt"
    if chemin_requirements.exists():
        try:
            requirements_texte = chemin_requirements.read_text(encoding="utf-8").lower()
        except OSError:
            requirements_texte = None

    for tech in TECHNOLOGIES:
        trouve = False
        if tech.fichiers_config:
            trouve = any((dossier / f).exists() for f in tech.fichiers_config)
        if not trouve and tech.paquets_npm:
            trouve = any(p in paquets for p in tech.paquets_npm)
        if not trouve and tech.sous_chaines_requirements and requirements_texte:
            trouve = any(s in requirements_texte for s in tech.sous_chaines_requirements)
        if not trouve and tech.contenu_fichier:
            for fichier, sous_chaine in tech.contenu_fichier:
                chemin = dossier / fichier
                if not chemin.exists():
                    continue
                try:
                    contenu = chemin.read_text(encoding="utf-8")
                except OSError:
                    continue
                if sous_chaine in contenu:
                    trouve = True
                    break
        if trouve:
            trouvees.add(tech.identifiant)
    return trouvees


def detecter_technologies(racine: Path) -> List[str]:
    """Les technologies réellement détectées sous `racine`, triées — liste
    vide sur un dossier vide ou sans preuve reconnue, jamais devinée."""
    racine = Path(racine)
    trouvees = _detecter_dans_dossier(racine)
    for sous_dossier in _sous_dossiers_a_sonder(racine):
        trouvees |= _detecter_dans_dossier(sous_dossier)
    return sorted(trouvees)


def detecter_combos(technologies: List[str]) -> List[str]:
    """Les combinaisons dont TOUTES les technologies requises sont présentes."""
    ensemble = set(technologies)
    return sorted(nom for nom, requis in COMBOS.items() if ensemble.issuperset(requis))
