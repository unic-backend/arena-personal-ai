"""Selection progressive du contexte projet pour les agents ARENA."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

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
