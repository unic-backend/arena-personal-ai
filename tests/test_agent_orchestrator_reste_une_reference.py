"""Agent Orchestrator reste une référence, jamais un runtime ARENA (DEC-0207).

L'audit `docs/audits/agent_orchestrator_audit.md` conclut Option C. AO est un
produit complet Go/Electron/SQLite/PTY avec sa propre persistance, ses propres
agents et une télémétrie distante active par défaut dans les releases. Un refus
documenté ne suffit pas : ces tests empêchent son entrée silencieuse sous forme
de dépendance, checkout, sous-module ou import Python.

La seconde moitié exécute une capacité native qui fonde la décision : un vrai
dépôt Git reçoit un worktree via `Atelier.isoler()`, le fichier créé dans ce
worktree ne touche pas l'arbre principal, puis le worktree est retiré. Ainsi,
le jour où l'isolation Git d'ARENA disparaît, la raison « AO n'est pas requis
pour les worktrees » se rouvre au lieu de rester vraie par inertie.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
NOMS_DEPENDANCE = ("agent-orchestrator", "agent_orchestrator", "aoagents/agent-orchestrator")
FICHIERS_DEPENDANCES_DIRECTES = (
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
)
_NOM_PAQUET = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(?:\[|==|~=|>=|<=|!=|<|>|;|$)")


def _commande(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), cwd=cwd, text=True, capture_output=True, check=False,
    )


def _fichiers_suivis() -> list[str]:
    resultat = _commande("git", "ls-files", cwd=RACINE)
    assert resultat.returncode == 0, resultat.stderr
    return [ligne for ligne in resultat.stdout.splitlines() if ligne]


def _dependances_directes(chemin: Path) -> set[str]:
    """Lit seulement les déclarations, jamais une mention explicative."""
    trouvees: set[str] = set()
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        nue = ligne.strip().strip('"').strip(",").strip()
        if not nue or nue.startswith(("#", "[", "-", "{")):
            continue
        correspondance = _NOM_PAQUET.match(nue)
        if correspondance:
            trouvees.add(correspondance.group(1).lower())
    return trouvees


def test_ao_n_est_pas_une_dependance_ni_un_checkout_suivi() -> None:
    coupables: list[str] = []
    for fichier in FICHIERS_DEPENDANCES_DIRECTES:
        chemin = RACINE / fichier
        if not chemin.exists():
            continue
        declarees = _dependances_directes(chemin)
        for nom in NOMS_DEPENDANCE:
            if nom in declarees:
                coupables.append(f"dépendance directe {fichier}: {nom}")
        # Le parseur ci-dessus couvre les paquets PyPI ordinaires. Une URL Git
        # n'a pas nécessairement un nom de paquet en tête : elle reste une
        # dépendance directe et doit donc tomber elle aussi, sans confondre les
        # commentaires de l'audit avec une déclaration.
        for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
            nue = ligne.strip().lower()
            if nue and not nue.startswith("#") and any(nom in nue for nom in NOMS_DEPENDANCE):
                coupables.append(f"dépendance directe {fichier}:{numero}: {ligne.strip()}")

    autorises = {
        "docs/audits/agent_orchestrator_audit.md",
        "docs/DECISIONS.md",
        "tests/test_agent_orchestrator_reste_une_reference.py",
    }
    for relatif in _fichiers_suivis():
        minuscules = relatif.lower()
        if relatif in autorises:
            continue
        if any(nom in minuscules for nom in NOMS_DEPENDANCE):
            coupables.append(f"contenu AO suivi: {relatif}")

    # Un sous-module n'est pas visible dans `git ls-files`; il est une autre
    # forme de checkout qui créerait un second produit dans le dépôt.
    sous_modules = _commande("git", "submodule", "status", cwd=RACINE)
    assert sous_modules.returncode == 0, sous_modules.stderr
    if any(nom in sous_modules.stdout.lower() for nom in NOMS_DEPENDANCE):
        coupables.append("sous-module Agent Orchestrator")

    assert not coupables, (
        "AO est devenu une dépendance ou un checkout ARENA malgré DEC-0207:\n  "
        + "\n  ".join(coupables)
    )


def test_aucun_code_python_suivi_n_importe_ao() -> None:
    coupables: list[str] = []
    for relatif in _fichiers_suivis():
        if not relatif.endswith(".py"):
            continue
        chemin = RACINE / relatif
        try:
            arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=relatif)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                modules = [alias.name for alias in noeud.names]
            elif isinstance(noeud, ast.ImportFrom):
                modules = [noeud.module or ""]
            else:
                continue
            for module in modules:
                normalise = module.lower().replace("_", "-")
                if normalise == "agent-orchestrator" or normalise.startswith("agent-orchestrator."):
                    coupables.append(f"{relatif}:{noeud.lineno} -> {module}")

    assert not coupables, (
        "Un import AO contourne la décision d’architecture DEC-0207:\n  "
        + "\n  ".join(coupables)
    )


def test_worktree_arena_reste_reellement_isole(tmp_path: Path) -> None:
    """La capacité locale vérifiée, pas seulement citée dans l'audit."""
    from tools.atelier.atelier import Atelier

    depot = tmp_path / "depot"
    depot.mkdir()
    for args in (
        ("git", "init"),
        ("git", "config", "user.email", "audit@example.invalid"),
        ("git", "config", "user.name", "Audit ARENA"),
    ):
        resultat = _commande(*args, cwd=depot)
        assert resultat.returncode == 0, resultat.stderr

    (depot / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (depot / "principal.txt").write_text("arbre principal\n", encoding="utf-8")
    resultat = _commande("git", "add", ".", cwd=depot)
    assert resultat.returncode == 0, resultat.stderr
    resultat = _commande("git", "commit", "-m", "base", cwd=depot)
    assert resultat.returncode == 0, resultat.stderr

    atelier = Atelier(racine=depot)
    cree = atelier.isoler("worker-audit")
    assert cree.ok, cree.erreur or cree.message
    worktree = Path(cree.donnees["chemin"])
    assert worktree.is_dir()
    assert ".worktrees" in str(worktree)
    assert ".worktrees/" in (depot / ".gitignore").read_text(encoding="utf-8")

    (worktree / "seulement-worker.txt").write_text("isole\n", encoding="utf-8")
    assert not (depot / "seulement-worker.txt").exists(), (
        "une écriture de worktree a atteint l'arbre principal"
    )

    # Le retrait normal ne force rien. Ici le worktree est rendu propre avant
    # nettoyage : aucune donnée de travail ne doit être détruite par le test.
    resultat = _commande("git", "clean", "-fd", cwd=worktree)
    assert resultat.returncode == 0, resultat.stderr
    retire = atelier.nettoyer_worktree("worker-audit")
    assert retire.ok, retire.erreur or retire.message
    assert not worktree.exists()


def test_audit_et_decision_restent_lisibles() -> None:
    audit = RACINE / "docs/audits/agent_orchestrator_audit.md"
    assert audit.exists(), "l’audit qui fonde DEC-0207 a disparu"
    texte = audit.read_text(encoding="utf-8").lower()
    for marqueur in (
        "option c",
        "posthog",
        "github_actor",
        "unknown — non mesuré",
        "aucun paquet",
    ):
        assert marqueur in texte, f"l’audit ne documente plus {marqueur!r}"

    decisions = (RACINE / "docs/DECISIONS.md").read_text(encoding="utf-8")
    assert "## DEC-0207" in decisions, "DEC-0207 a disparu du registre"
