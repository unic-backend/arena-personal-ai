"""État Git structuré — mission ARENA x GITGUI (11/09/2026, DEC-0093).

`Atelier.git()` (DEC-0038) donne à Dioumtoukay `git` en shell nu — aucune
garde, ce qui reste entier ici. Ce module ne le remplace pas : il ajoute une
LECTURE structurée de ce que `git status`/`git diff` disent déjà, pour que
Dioumtoukay (et le futur agent d'auto-réparation) raisonnent sur des champs
typés plutôt que sur du texte à reparser à chaque fois — et une paire
`creer_checkpoint()`/`restaurer_checkpoint()` pour qu'une réparation ratée
puisse annuler SES PROPRES modifications sans jamais toucher un fichier que
le propriétaire avait déjà modifié avant qu'elle ne commence.

Audit réel avant d'écrire une ligne : `antonellof/gitgui` (MIT, commit
`7b08381`) modélise exactement ce dont manquait ARENA — `RepoSnapshot`,
`FileStatus`, `RepoState` dans `src/git/repo.rs` — sur `git2` (libgit2).
**Rien de son code Rust n'est copié.** ARENA n'ajoute pas de dépendance
`git2`/libgit2 : `git status --porcelain=v2 --branch` est un format stable,
documenté, MACHINE-lisible (contrairement au format humain `--short`), et
`Atelier.executer()` sait déjà lancer une commande shell — pas de
bibliothèque neuve, juste un format de sortie mieux choisi. Détail complet :
`docs/audits/gitgui_audit.md`.

**Ce qui n'est délibérément PAS repris d'ici** : aucune garde n'est ajoutée
à `Atelier.git()`/`executer()` — DEC-0038 reste entier, non re-litigé. Une
branche « protégée » (`branche_protegee()`) est un CHAMP INFORMATIF sur
`EtatGit`, jamais un refus : c'est à l'appelant (un futur agent
d'auto-réparation, pas Dioumtoukay aujourd'hui) de choisir quoi en faire.
"""
from __future__ import annotations

import re
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

#: Délai par défaut d'une commande git de lecture — un `git status` sur un
#: gros dépôt peut prendre plus qu'un instant, mais jamais aussi longtemps
#: qu'une commande arbitraire (`Atelier.DELAI_PAR_DEFAUT`, 120s).
DELAI_PAR_DEFAUT = 20.0

#: Sans configuration explicite, ce que ce dépôt considère comme protégé.
#: Un champ informatif seulement (voir la note ci-dessus) — jamais un refus.
BRANCHES_PROTEGEES_PAR_DEFAUT = frozenset({"main", "master"})


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StatutFichier(str, Enum):
    """Le même vocabulaire que `FileKind` de gitgui (`src/git/repo.rs`) —
    concept repris, aucune ligne copiée."""

    AJOUTE = "AJOUTE"
    MODIFIE = "MODIFIE"
    SUPPRIME = "SUPPRIME"
    RENOMME = "RENOMME"
    COPIE = "COPIE"
    TYPE_CHANGE = "TYPE_CHANGE"
    NON_SUIVI = "NON_SUIVI"
    CONFLIT = "CONFLIT"


_LETTRE_VERS_STATUT: Dict[str, StatutFichier] = {
    "A": StatutFichier.AJOUTE, "M": StatutFichier.MODIFIE, "D": StatutFichier.SUPPRIME,
    "R": StatutFichier.RENOMME, "C": StatutFichier.COPIE, "T": StatutFichier.TYPE_CHANGE,
}


@dataclass(frozen=True)
class EtatFichier:
    """Un fichier et ce qui lui est arrivé, dans l'index ou l'arbre de travail."""

    chemin: str
    statut: StatutFichier
    ancien_chemin: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        d = {"chemin": self.chemin, "statut": self.statut.value}
        if self.ancien_chemin:
            d["ancien_chemin"] = self.ancien_chemin
        return d


class EtatOperation(str, Enum):
    """Une opération git en cours — même idée que `RepoState` de gitgui.
    `PROPRE` : rien en cours, jamais confondu avec `Aucun fichier modifié`."""

    PROPRE = "PROPRE"
    FUSION = "FUSION"
    REBASE = "REBASE"
    CHERRY_PICK = "CHERRY_PICK"
    REVERT = "REVERT"
    BISECT = "BISECT"


@dataclass
class EtatGit:
    """L'état structuré d'un dépôt, à l'instant où il a été mesuré."""

    racine: Path
    branche: Optional[str]
    detachee: bool
    tete: Optional[str]
    amont: Optional[str] = None
    en_avance: int = 0
    en_retard: int = 0
    modifies: List[EtatFichier] = field(default_factory=list)
    indexes: List[EtatFichier] = field(default_factory=list)
    non_suivis: List[EtatFichier] = field(default_factory=list)
    conflits: List[EtatFichier] = field(default_factory=list)
    operation: EtatOperation = EtatOperation.PROPRE
    mesure_le: str = field(default_factory=_maintenant)

    @property
    def propre(self) -> bool:
        """Aucun fichier modifié, indexé, non suivi ou en conflit."""
        return not (self.modifies or self.indexes or self.non_suivis or self.conflits)

    def branche_protegee(self, protegees: FrozenSet[str] = BRANCHES_PROTEGEES_PAR_DEFAUT) -> bool:
        """Champ INFORMATIF — voir la note du module. Jamais un refus ici."""
        return bool(self.branche) and self.branche in protegees

    def to_dict(self) -> Dict[str, object]:
        return {
            "racine": str(self.racine),
            "branche": self.branche,
            "detachee": self.detachee,
            "tete": self.tete,
            "amont": self.amont,
            "en_avance": self.en_avance,
            "en_retard": self.en_retard,
            "modifies": [f.to_dict() for f in self.modifies],
            "indexes": [f.to_dict() for f in self.indexes],
            "non_suivis": [f.to_dict() for f in self.non_suivis],
            "conflits": [f.to_dict() for f in self.conflits],
            "operation": self.operation.value,
            "propre": self.propre,
            "branche_protegee": self.branche_protegee(),
            "mesure_le": self.mesure_le,
        }


class ErreurGit(Exception):
    """Une commande git a échoué — jamais avalée, jamais devinée."""

    def __init__(self, commande: List[str], code: Optional[int], message: str) -> None:
        self.commande = commande
        self.code = code
        super().__init__(message)


def _executer(racine: Path, arguments: List[str], delai: float) -> str:
    try:
        fini = subprocess.run(  # noqa: S603 — meme discipline que Atelier.executer
            ["git", *arguments], cwd=str(racine), capture_output=True, text=True,
            timeout=delai, check=False)
    except FileNotFoundError as erreur:
        raise ErreurGit(arguments, None, f"git introuvable : {erreur}") from erreur
    except subprocess.TimeoutExpired as erreur:
        raise ErreurGit(arguments, None, f"commande arretee apres {delai:.0f}s") from erreur
    if fini.returncode != 0:
        raise ErreurGit(arguments, fini.returncode, fini.stderr.strip() or fini.stdout.strip())
    return fini.stdout


def _git_dir(racine: Path, delai: float) -> Optional[Path]:
    """`git rev-parse --git-dir` — jamais supposer `.git/`, qui peut être un
    fichier (worktree, `Atelier.isoler()`, DEC-0091) plutôt qu'un dossier."""
    try:
        sortie = _executer(racine, ["rev-parse", "--git-dir"], delai)
    except ErreurGit:
        return None
    chemin = Path(sortie.strip())
    return chemin if chemin.is_absolute() else racine / chemin


def _operation_en_cours(racine: Path, delai: float) -> EtatOperation:
    """Un merge/rebase/cherry-pick/revert/bisect en cours se lit dans des
    fichiers connus sous le git-dir — jamais deviné autrement (même
    principe que `RepoState` de gitgui, détection réimplémentée ici)."""
    gd = _git_dir(racine, delai)
    if gd is None:
        return EtatOperation.PROPRE
    if (gd / "MERGE_HEAD").exists():
        return EtatOperation.FUSION
    if (gd / "CHERRY_PICK_HEAD").exists():
        return EtatOperation.CHERRY_PICK
    if (gd / "REVERT_HEAD").exists():
        return EtatOperation.REVERT
    if (gd / "rebase-merge").is_dir() or (gd / "rebase-apply").is_dir():
        return EtatOperation.REBASE
    if (gd / "BISECT_LOG").exists():
        return EtatOperation.BISECT
    return EtatOperation.PROPRE


_LIGNE_BRANCHE = re.compile(r"^# branch\.(\S+)(?:\s+(.*))?$")
_LIGNE_AB = re.compile(r"^\+(\d+)\s+-(\d+)$")


def lire_etat(racine: Path, delai: float = DELAI_PAR_DEFAUT) -> EtatGit:
    """L'état réel du dépôt à `racine`, mesuré — jamais supposé.

    Parse `git status --porcelain=v2 --branch`, le format MACHINE (stable,
    documenté par `git-status(1)`), jamais le format `--short` pensé pour un
    humain et ambigu à reparser (espaces dans les noms de fichiers, lettres
    qui se ressemblent).
    """
    sortie = _executer(racine, ["status", "--porcelain=v2", "--branch"], delai)

    branche: Optional[str] = None
    detachee = False
    tete: Optional[str] = None
    amont: Optional[str] = None
    en_avance = en_retard = 0
    modifies: List[EtatFichier] = []
    indexes: List[EtatFichier] = []
    non_suivis: List[EtatFichier] = []
    conflits: List[EtatFichier] = []

    for ligne in sortie.splitlines():
        if not ligne:
            continue
        if ligne.startswith("# branch."):
            m = _LIGNE_BRANCHE.match(ligne)
            if not m:
                continue
            cle, valeur = m.group(1), (m.group(2) or "").strip()
            if cle == "oid":
                tete = None if valeur == "(initial)" else valeur
            elif cle == "head":
                if valeur == "(detached)":
                    detachee = True
                else:
                    branche = valeur
            elif cle == "upstream":
                amont = valeur
            elif cle == "ab":
                ma = _LIGNE_AB.match(valeur)
                if ma:
                    en_avance, en_retard = int(ma.group(1)), int(ma.group(2))
            continue

        if ligne.startswith("? "):
            non_suivis.append(EtatFichier(ligne[2:], StatutFichier.NON_SUIVI))
            continue
        if ligne.startswith("! "):
            continue  # ignoré (.gitignore) : ni modifie, ni a suivre

        if ligne.startswith("u "):
            # Fusion en conflit : "u <XY> <sub> ... <chemin>"
            morceaux = ligne.split(" ", 10)
            if len(morceaux) >= 11:
                conflits.append(EtatFichier(morceaux[10], StatutFichier.CONFLIT))
            continue

        if ligne.startswith("1 ") or ligne.startswith("2 "):
            morceaux = ligne.split(" ")
            xy = morceaux[1]
            reste = ligne.split(" ", 8)[-1] if ligne.startswith("1 ") else ligne.split(" ", 9)[-1]
            if ligne.startswith("2 "):
                # Renommage/copie : "2 <XY> ... <score> <chemin>\t<ancien_chemin>"
                chemin, _, ancien = reste.partition("\t")
            else:
                chemin, ancien = reste, None
            x_index, y_travail = xy[0], xy[1]
            if x_index != ".":
                statut = _LETTRE_VERS_STATUT.get(x_index, StatutFichier.MODIFIE)
                indexes.append(EtatFichier(chemin, statut, ancien))
            if y_travail != ".":
                statut = _LETTRE_VERS_STATUT.get(y_travail, StatutFichier.MODIFIE)
                modifies.append(EtatFichier(chemin, statut, ancien))
            continue

    return EtatGit(
        racine=racine, branche=branche, detachee=detachee, tete=tete, amont=amont,
        en_avance=en_avance, en_retard=en_retard, modifies=modifies, indexes=indexes,
        non_suivis=non_suivis, conflits=conflits,
        operation=_operation_en_cours(racine, delai))


# --- Diff structuré ----------------------------------------------------------------

@dataclass(frozen=True)
class DiffFichier:
    """Le diff unifié d'un seul fichier, avec son statut."""

    chemin: str
    statut: StatutFichier
    texte: str
    ancien_chemin: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        d = {"chemin": self.chemin, "statut": self.statut.value, "texte": self.texte}
        if self.ancien_chemin:
            d["ancien_chemin"] = self.ancien_chemin
        return d


_ENTETE_DIFF = re.compile(r"^diff --git a/(.*) b/(.*)$", re.MULTILINE)


def _decouper_par_fichier(texte_diff: str) -> List[str]:
    """Sépare une sortie `git diff` en un bloc par fichier."""
    if not texte_diff:
        return []
    blocs: List[str] = []
    courant: List[str] = []
    for ligne in texte_diff.splitlines(keepends=True):
        if ligne.startswith("diff --git ") and courant:
            blocs.append("".join(courant))
            courant = [ligne]
        else:
            courant.append(ligne)
    if courant:
        blocs.append("".join(courant))
    return blocs


def _statut_du_bloc(bloc: str) -> StatutFichier:
    if "\nnew file mode" in bloc or bloc.startswith("new file mode"):
        return StatutFichier.AJOUTE
    if "\ndeleted file mode" in bloc or bloc.startswith("deleted file mode"):
        return StatutFichier.SUPPRIME
    if "\nrename from " in bloc:
        return StatutFichier.RENOMME
    if "\ncopy from " in bloc:
        return StatutFichier.COPIE
    return StatutFichier.MODIFIE


def lire_diff(racine: Path, cible: str = "travail", chemins: Optional[List[str]] = None,
             contexte: int = 3, delai: float = DELAI_PAR_DEFAUT) -> List[DiffFichier]:
    """Le diff structuré, par fichier.

    Args:
        cible: `"travail"` (arbre de travail contre l'index — le même diff
            que `git status` marque en Y), `"index"` (index contre HEAD — ce
            qu'un commit contiendrait), ou un identifiant de commit (son
            diff contre son parent, via `git show`).
        chemins: limite le diff a ces chemins (relatifs a `racine`), ou tout
            le depot si vide.
    """
    if cible == "travail":
        arguments = ["diff", "--no-color", f"-U{contexte}"]
    elif cible == "index":
        arguments = ["diff", "--no-color", "--cached", f"-U{contexte}"]
    else:
        arguments = ["show", "--no-color", f"-U{contexte}", "--format=", cible]
    if chemins:
        arguments += ["--", *chemins]

    sortie = _executer(racine, arguments, delai)
    resultat: List[DiffFichier] = []
    for bloc in _decouper_par_fichier(sortie):
        entete = _ENTETE_DIFF.search(bloc)
        if not entete:
            continue
        chemin_a, chemin_b = entete.group(1), entete.group(2)
        statut = _statut_du_bloc(bloc)
        ancien = chemin_a if statut in (StatutFichier.RENOMME, StatutFichier.COPIE) and \
            chemin_a != chemin_b else None
        resultat.append(DiffFichier(chemin=chemin_b, statut=statut, texte=bloc, ancien_chemin=ancien))
    return resultat


# --- Checkpoint / restauration ------------------------------------------------------

@dataclass(frozen=True)
class Checkpoint:
    """Un point de reprise : ce qui était déjà en désordre AVANT qu'un agent
    ne commence à travailler. `fichiers_preexistants` n'est jamais touché
    par `restaurer_checkpoint()` — c'est la garantie qui protège le travail
    du propriétaire (mission ARENA x GITGUI, « never overwrite unrelated
    changes »)."""

    identifiant: str
    racine: Path
    branche: Optional[str]
    tete: Optional[str]
    fichiers_preexistants: FrozenSet[str]
    cree_le: str

    def to_dict(self) -> Dict[str, object]:
        return {"identifiant": self.identifiant, "branche": self.branche, "tete": self.tete,
                "fichiers_preexistants": sorted(self.fichiers_preexistants),
                "cree_le": self.cree_le}


def _chemins_dirty(etat: EtatGit) -> set:
    return ({f.chemin for f in etat.modifies} | {f.chemin for f in etat.indexes}
            | {f.chemin for f in etat.non_suivis} | {f.chemin for f in etat.conflits})


def creer_checkpoint(racine: Path, delai: float = DELAI_PAR_DEFAUT) -> Checkpoint:
    """Photographie l'état actuel — À APPELER AVANT toute modification par
    un agent. Rejoue `lire_etat()`, ne fait rien d'autre : aucun `git
    stash`, aucun commit, aucune écriture — un checkpoint qui modifiait le
    dépôt pour le protéger serait absurde."""
    etat = lire_etat(racine, delai)
    return Checkpoint(
        identifiant=uuid.uuid4().hex[:12], racine=racine, branche=etat.branche, tete=etat.tete,
        fichiers_preexistants=frozenset(_chemins_dirty(etat)), cree_le=_maintenant())


def fichiers_touches_depuis(checkpoint: Checkpoint, delai: float = DELAI_PAR_DEFAUT) -> List[str]:
    """Les chemins dirty MAINTENANT qui ne l'étaient PAS au checkpoint —
    ce qu'un agent (ou n'importe quoi d'autre) a changé depuis."""
    etat = lire_etat(checkpoint.racine, delai)
    return sorted(_chemins_dirty(etat) - checkpoint.fichiers_preexistants)


@dataclass(frozen=True)
class ResultatRestauration:
    restaures: List[str]
    echecs: List[Dict[str, str]]
    ignores_deja_dirty: List[str]

    @property
    def ok(self) -> bool:
        return not self.echecs

    def to_dict(self) -> Dict[str, object]:
        return {"restaures": self.restaures, "echecs": self.echecs,
                "ignores_deja_dirty": self.ignores_deja_dirty, "ok": self.ok}


def restaurer_checkpoint(checkpoint: Checkpoint, delai: float = DELAI_PAR_DEFAUT) -> ResultatRestauration:
    """Annule UNIQUEMENT les fichiers touchés depuis le checkpoint.

    Pour chaque chemin : s'il existait à HEAD, `git checkout HEAD --
    <chemin>` restaure le contenu exact de HEAD (index ET arbre de travail —
    efface aussi bien une modification qu'une mise en index) ; sinon (créé
    par l'agent depuis le checkpoint), désindexé puis supprimé du disque.

    Un fichier déjà dans `fichiers_preexistants` n'est **jamais** examiné —
    ce n'est pas un filtre appliqué ici, c'est `fichiers_touches_depuis()`
    qui ne le renvoie structurellement jamais.

    **Limite délibérée, mesurée en écrivant ce module** : la granularité est
    le FICHIER, jamais le contenu. Si un fichier était déjà modifié par le
    propriétaire au moment du checkpoint, et qu'un agent y ajoute ENCORE des
    changements ensuite, ce fichier n'est PAS restauré — ni partiellement ni
    entièrement. Une restauration au contenu de HEAD effacerait aussi la
    modification du propriétaire (l'erreur que la mission interdit en premier :
    « never overwrite unrelated changes ») ; séparer chirurgicalement les deux
    contributions demanderait un diff à trois voies que ce module ne construit
    pas. Le choix sûr est donc de ne rien faire sur ce fichier précis — il
    reste tel quel, avec les deux modifications mélangées, et l'appelant doit
    le savoir : c'est exactement `ignores_deja_dirty` sur le résultat.
    """
    racine = checkpoint.racine
    a_traiter = fichiers_touches_depuis(checkpoint, delai)
    restaures: List[str] = []
    echecs: List[Dict[str, str]] = []
    for chemin in a_traiter:
        try:
            existe_a_tete = checkpoint.tete is not None and subprocess.run(
                ["git", "cat-file", "-e", f"{checkpoint.tete}:{chemin}"],
                cwd=str(racine), capture_output=True, timeout=delai, check=False,
            ).returncode == 0
            if existe_a_tete:
                _executer(racine, ["checkout", checkpoint.tete, "--", chemin], delai)
            else:
                # Cree depuis le checkpoint : desindexer (au cas ou stage), puis effacer.
                subprocess.run(["git", "reset", "-q", "--", chemin], cwd=str(racine),
                              capture_output=True, timeout=delai, check=False)
                cible = racine / chemin
                if cible.is_file():
                    cible.unlink()
            restaures.append(chemin)
        except (ErreurGit, OSError) as erreur:
            echecs.append({"chemin": chemin, "erreur": str(erreur)})
    return ResultatRestauration(
        restaures=restaures, echecs=echecs,
        ignores_deja_dirty=sorted(checkpoint.fichiers_preexistants))
