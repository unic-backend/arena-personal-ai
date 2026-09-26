"""Selection progressive du contexte projet pour les agents ARENA."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

RACINE = Path(__file__).resolve().parents[2]
MEMOIRE_PROJET = RACINE / "PROJECT_MEMORY"
TOUJOURS = ("PROJECT_MAP.md", "ACTIVE_WORK.md", "LOCKED_ZONES.md")
REGLES = (
    (("architecture", "agent", "orchestr", "connector", "mcp"), ("ARCHITECTURE.md", "DEPENDENCIES.md")),
    (("dependency", "dependance", "package", "library", "framework"), ("DEPENDENCIES.md",)),
    (("decision", "choix", "pourquoi"), ("DECISIONS.md",)),
    (("complete", "deja", "existing", "existant", "regression"), ("COMPLETED_SYSTEMS.md",)),
    (("history", "historique", "previous", "precedent", "changelog"), ("CHANGELOG.md",)),
)

@dataclass(frozen=True)
class ContexteProjet:
    fichiers: tuple[str, ...]
    contenu: str
    caracteres: int
    tronque: bool

@dataclass(frozen=True)
class EntreeContexteProjet:
    fichier: str
    titre: str
    contenu: str
    score: int

@dataclass(frozen=True)
class ResolutionContexteProjet:
    tache: str
    entrees: tuple[EntreeContexteProjet, ...]
    caracteres: int
    tronque: bool

def fichiers_pour_tache(tache: str) -> tuple[str, ...]:
    texte = tache.casefold()
    noms = list(TOUJOURS)
    for mots, fichiers in REGLES:
        if any(mot in texte for mot in mots):
            noms.extend(fichiers)
    return tuple(dict.fromkeys(noms))

def charger_contexte_projet(tache: str, budget_caracteres: int = 24_000) -> ContexteProjet:
    if budget_caracteres < 1:
        raise ValueError("budget_caracteres doit etre >= 1")
    morceaux: list[str] = []
    utilises: list[str] = []
    restant, tronque = budget_caracteres, False
    for nom in fichiers_pour_tache(tache):
        chemin = MEMOIRE_PROJET / nom
        if not chemin.is_file():
            continue
        bloc = f"# {nom}\n{chemin.read_text(encoding='utf-8').strip()}\n"
        if len(bloc) > restant:
            if restant:
                morceaux.append(bloc[:restant])
            utilises.append(nom)
            tronque = True
            break
        morceaux.append(bloc)
        utilises.append(nom)
        restant -= len(bloc)
    contenu = "\n".join(morceaux)
    return ContexteProjet(tuple(utilises), contenu, len(contenu), tronque)


def _termes(texte: str) -> set[str]:
    ponctuation = ".,;:!?()[]{}\"'"
    return {mot.strip(ponctuation).casefold() for mot in texte.split() if len(mot.strip(ponctuation)) >= 3}


def _blocs_markdown(contenu: str) -> Iterable[tuple[str, str]]:
    titre = "Document"
    lignes: list[str] = []
    for ligne in contenu.splitlines():
        if ligne.startswith("#"):
            if lignes:
                yield titre, "\n".join(lignes).strip()
            titre = ligne.lstrip("#").strip() or "Section"
            lignes = []
        else:
            lignes.append(ligne)
    if lignes:
        yield titre, "\n".join(lignes).strip()


def rechercher_contexte_projet(requete: str, *, limite: int = 8) -> tuple[EntreeContexteProjet, ...]:
    """Recherche locale dans PROJECT_MEMORY, avec provenance et sans second index."""
    if limite < 1:
        raise ValueError("limite doit etre >= 1")
    termes = _termes(requete)
    if not termes or not MEMOIRE_PROJET.is_dir():
        return ()
    resultats: list[EntreeContexteProjet] = []
    for chemin in sorted(MEMOIRE_PROJET.glob("*.md")):
        try:
            contenu = chemin.read_text(encoding="utf-8")
        except OSError:
            continue
        for titre, bloc in _blocs_markdown(contenu):
            score = len(termes & _termes(f"{titre}\n{bloc}"))
            if score:
                resultats.append(EntreeContexteProjet(chemin.name, titre, bloc, score))
    resultats.sort(key=lambda entree: (-entree.score, entree.fichier, entree.titre))
    return tuple(resultats[:limite])


def resoudre_contexte_projet(tache: str, *, budget_caracteres: int = 24_000, limite_recherche: int = 8) -> ResolutionContexteProjet:
    """Résout un contexte borné pour une tâche, inspiré de potpie resolve."""
    if budget_caracteres < 1:
        raise ValueError("budget_caracteres doit etre >= 1")
    candidats: list[EntreeContexteProjet] = []
    vus: set[tuple[str, str]] = set()
    for nom in fichiers_pour_tache(tache):
        chemin = MEMOIRE_PROJET / nom
        try:
            contenu = chemin.read_text(encoding="utf-8")
        except OSError:
            continue
        for titre, bloc in _blocs_markdown(contenu):
            cle = (nom, titre)
            if cle not in vus:
                vus.add(cle)
                candidats.append(EntreeContexteProjet(nom, titre, bloc, 100))
    for entree in rechercher_contexte_projet(tache, limite=limite_recherche):
        cle = (entree.fichier, entree.titre)
        if cle not in vus:
            vus.add(cle)
            candidats.append(entree)
    retenues: list[EntreeContexteProjet] = []
    utilises = 0
    tronque = False
    for entree in candidats:
        cout = len(entree.titre) + len(entree.contenu)
        if utilises + cout > budget_caracteres:
            tronque = True
            break
        retenues.append(entree)
        utilises += cout
    return ResolutionContexteProjet(tache, tuple(retenues), utilises, tronque)
