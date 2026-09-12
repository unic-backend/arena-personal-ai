"""Opérations Git mutantes, structurées — mission ARENA x GITGUI, second
passage (DEC-0094).

`git_etat.py` (DEC-0093) donne une LECTURE structurée du dépôt (état, diff,
checkpoint/restauration). `Atelier.git()` (DEC-0038) donne l'ÉCRITURE sans
aucune garde — shell nu, rien d'interdit, rien à confirmer. Ce module ajoute
une TROISIÈME chose, qui ne remplace ni l'une ni l'autre : des opérations
mutantes structurées, sûres à rejouer, qui vérifient ce qu'elles ont
réellement fait plutôt que de le supposer.

Audit réel avant d'écrire une ligne : `antonellof/gitgui` (MIT, commit
`7b08381`), `docs/SPEC.md` section 7 et `src/agent.rs` — son API de contrôle
pour agent (douze commandes JSON, un identifiant optionnel par écriture, un
dictionnaire en mémoire `agent_results` plafonné à 256 entrées qui rend le
résultat déjà obtenu — jamais une deuxième exécution — quand le même
identifiant revient). **Rien de son code Rust n'est copié** : le mécanisme
(pas le code) est réimplémenté ici en Python, sur la structure déjà en place
(`git_etat.py`, `verrous.py`).

Différence architecturale délibérée, et pas un oubli : gitgui fait tourner
l'interface graphique et le git worker dans des THREADS SÉPARÉS d'un même
process Rust, reliés par un socket Unix pour qu'un agent dans un AUTRE
process (un terminal voisin) puisse piloter l'interface. ARENA n'a jamais eu
cette frontière : Dioumtoukay et `Atelier` tournent dans le MÊME process
Python, et un appel de méthode EST déjà le canal de contrôle que le socket
Unix existe pour fournir chez eux. Ouvrir un socket ici recréerait une
frontière de process qui n'existe pas, pour aucun bénéfice — voir
`docs/audits/gitgui_audit.md` (édition DEC-0094) pour le détail complet.

**Ce qui n'est délibérément PAS ajouté ici, et pourquoi** :

- `reset --hard`, `clean -fd`, suppression de branche/tag distante, réécriture
  d'historique (`rebase -i` sur des commits déjà partagés) : absents de la
  liste d'opérations que la mission elle-même énumère (section 6) et
  délibérément non enveloppés — DEC-0038 reste la seule porte pour ce
  registre, via `Atelier.git()` en toutes lettres, jamais un défaut silencieux
  ici. Ajouter une confirmation nouvelle pour ces opérations reviendrait à
  retirer en douce ce que DEC-0038 a explicitement accordé — non re-litigé.
- `--force` nu : n'existe PAS dans cette API, même comme paramètre. Seul
  `--force-with-lease` est exposé (mission §14), et seulement quand l'appelant
  le demande explicitement.
- Un « AI commit message » séparé : Dioumtoukay EST déjà l'agent qui rédige
  ses messages de commit — doublon direct, déjà refusé en DEC-0093.
"""
from __future__ import annotations

import re
import subprocess
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.atelier import git_etat, verrous

#: Même délai que les lectures (`git_etat.DELAI_PAR_DEFAUT`) — une opération
#: d'écriture locale (commit, stage, checkout) n'a aucune raison de prendre
#: plus longtemps qu'une lecture. Les opérations réseau (fetch/pull/push) le
#: dépassent explicitement (voir `DELAI_RESEAU_PAR_DEFAUT`).
DELAI_PAR_DEFAUT = git_etat.DELAI_PAR_DEFAUT

#: Le réseau peut être lent ; ne pas le confondre avec une commande bloquée
#: par erreur. Toujours nettement sous `Atelier.DELAI_PAR_DEFAUT` (120s) —
#: une opération réseau qui dépasse ça a un problème réel à rapporter, pas à
#: laisser courir plus longtemps encore.
DELAI_RESEAU_PAR_DEFAUT = 60.0

#: Combien de résultats d'opérations (par identifiant d'idempotence) sont
#: gardés en mémoire — même chiffre que `AGENT_RESULTS_KEPT` de gitgui
#: (`src/ui/app.rs`), une convention reprise telle quelle, pas mesurée
#: différemment ici faute de raison de diverger.
CAPACITE_JOURNAL = 256


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Classification d'erreurs -------------------------------------------------------

class TypeErreurGit(str, Enum):
    """Une erreur git classée — jamais laissée comme texte brut à deviner par
    l'appelant. Vocabulaire de la mission (§29), traduit."""

    NON_UN_DEPOT = "NON_UN_DEPOT"
    ARBRE_SALE = "ARBRE_SALE"
    CONFLIT = "CONFLIT"
    ECHEC_AUTH = "ECHEC_AUTH"
    NON_FAST_FORWARD = "NON_FAST_FORWARD"
    DISTANT_INACCESSIBLE = "DISTANT_INACCESSIBLE"
    BRANCHE_INTROUVABLE = "BRANCHE_INTROUVABLE"
    HEAD_DETACHEE = "HEAD_DETACHEE"
    FICHIER_VERROU = "FICHIER_VERROU"
    REBASE_EN_COURS = "REBASE_EN_COURS"
    FUSION_EN_COURS = "FUSION_EN_COURS"
    PERMISSION_REFUSEE = "PERMISSION_REFUSEE"
    RIEN_A_FAIRE = "RIEN_A_FAIRE"
    INCONNUE = "INCONNUE"


#: Ordre important : le premier motif qui correspond gagne. Les motifs les
#: plus spécifiques passent avant les plus génériques.
_MOTIFS_ERREUR: List[tuple] = [
    (re.compile(r"not a git repository", re.IGNORECASE), TypeErreurGit.NON_UN_DEPOT),
    (re.compile(r"index\.lock|unable to create.*\.lock", re.IGNORECASE), TypeErreurGit.FICHIER_VERROU),
    (re.compile(r"conflict", re.IGNORECASE), TypeErreurGit.CONFLIT),
    (re.compile(r"authentication failed|could not read username|"
                r"permission denied \(publickey\)|invalid credentials", re.IGNORECASE),
     TypeErreurGit.ECHEC_AUTH),
    (re.compile(r"non-fast-forward|\[rejected\]|fetch first|"
                r"tip of your current branch is behind", re.IGNORECASE),
     TypeErreurGit.NON_FAST_FORWARD),
    (re.compile(r"could not resolve host|unable to access|"
                r"connection timed out|could not connect", re.IGNORECASE),
     TypeErreurGit.DISTANT_INACCESSIBLE),
    (re.compile(r"pathspec .* did not match|unknown revision|"
                r"not a valid ref|did not match any file", re.IGNORECASE),
     TypeErreurGit.BRANCHE_INTROUVABLE),
    (re.compile(r"rebase in progress|rebase-merge|rebase-apply", re.IGNORECASE),
     TypeErreurGit.REBASE_EN_COURS),
    (re.compile(r"already an? (merge|cherry-pick|revert) in progress|"
                r"merging is not possible", re.IGNORECASE),
     TypeErreurGit.FUSION_EN_COURS),
    (re.compile(r"permission denied", re.IGNORECASE), TypeErreurGit.PERMISSION_REFUSEE),
    (re.compile(r"nothing to commit|working tree clean|"
                r"nothing added to commit", re.IGNORECASE), TypeErreurGit.RIEN_A_FAIRE),
]


def classer_erreur(message: str) -> TypeErreurGit:
    """Classe un message d'erreur git — jamais rendu comme texte brut à
    interpréter à l'aveugle par l'appelant (mission §29)."""
    for motif, type_ in _MOTIFS_ERREUR:
        if motif.search(message or ""):
            return type_
    return TypeErreurGit.INCONNUE


# --- Sécurité des arguments ------------------------------------------------------------

def _commence_par_option(valeur: str) -> bool:
    """Vrai si `valeur` NE PEUT PAS être passée telle quelle à git comme
    référence nue (branche, distant, expression de révision), sans risque
    qu'elle soit lue comme une OPTION plutôt que comme la valeur voulue
    (mission §38, « branch names beginning with flags »).

    **Mesuré, pas supposé** : `git branch -D <depuis>` exécute réellement une
    suppression de branche quand `nom="-D"` est passé nu — confirmé en
    écrivant un dépôt de test avant ce correctif. `git checkout <nom> --`
    (le `--` en fin d'argument, censé lever l'ambiguïté chemin/référence)
    NE PROTÈGE PAS non plus : `git checkout` analyse ses options avant
    d'atteindre le `--`, donc `-D` y est encore lu comme un commutateur
    inconnu plutôt que comme une branche. La seule protection qui tienne
    dans tous les cas est de refuser toute valeur qui COMMENCE par `-` avant
    même de construire la commande — jamais une confiance dans `--` seul.

    Volontairement PLUS LARGE que `_nom_ref_invalide` : une EXPRESSION DE
    RÉVISION (`HEAD~1`, `main^2`, `origin/main`) est légitime ici et ne doit
    pas être refusée pour un `~`/`^`/`/` qui serait, lui, invalide dans un
    nom de branche à CRÉER."""
    return not valeur or valeur.startswith("-")


def _nom_ref_invalide(valeur: str) -> bool:
    """Vrai si `valeur` n'est pas un nom valide pour une référence à CRÉER
    (branche, tag) — les caractères que `git-check-ref-format(1)` refuse de
    toute façon, plus le préfixe `-` (`_commence_par_option`)."""
    if _commence_par_option(valeur):
        return True
    return any(c in valeur for c in (" ", "..", "~", "^", ":", "?", "*", "[", "\\", "\x00"))


# --- Résultat structuré --------------------------------------------------------------

@dataclass
class ResultatOperation:
    """Le résultat d'UNE opération git mutante — jamais du texte de terminal
    à deviner (mission §28)."""

    operation: str
    ok: bool
    message: str
    identifiant_operation: Optional[str] = None
    doublon: bool = False
    tete_avant: Optional[str] = None
    tete_apres: Optional[str] = None
    type_erreur: Optional[TypeErreurGit] = None
    sortie: str = ""
    donnees: Dict[str, Any] = field(default_factory=dict)
    horodatage: str = field(default_factory=_maintenant)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "operation": self.operation, "ok": self.ok, "message": self.message,
            "doublon": self.doublon, "tete_avant": self.tete_avant,
            "tete_apres": self.tete_apres, "horodatage": self.horodatage,
        }
        if self.identifiant_operation:
            d["identifiant_operation"] = self.identifiant_operation
        if self.type_erreur:
            d["type_erreur"] = self.type_erreur.value
        if self.donnees:
            d["donnees"] = self.donnees
        return d


class ErreurPreconditionGit(Exception):
    """Le HEAD réel ne correspond pas au HEAD attendu par l'appelant — la
    mutation demandée est refusée SANS s'exécuter (mission §8/§25/§33) :
    « detect concurrent changes, refuse or replan », jamais muter un dépôt
    qui a changé de façon inattendue."""

    def __init__(self, tete_attendue: str, tete_reelle: Optional[str]) -> None:
        self.tete_attendue = tete_attendue
        self.tete_reelle = tete_reelle
        super().__init__(
            f"HEAD attendu {tete_attendue}, HEAD reel {tete_reelle or '(aucun)'} "
            "— le depot a change, operation refusee.")


# --- Journal d'opérations + idempotence -----------------------------------------------

@dataclass(frozen=True)
class EntreeJournal:
    """Une ligne du journal d'opérations (mission §27) — jamais de secret,
    jamais la sortie complète d'une commande, juste ce qu'il faut pour
    diagnostiquer, reprendre, prouver l'idempotence."""

    identifiant_operation: Optional[str]
    operation: str
    racine: str
    tete_avant: Optional[str]
    tete_apres: Optional[str]
    ok: bool
    horodatage: str

    def to_dict(self) -> Dict[str, Any]:
        return {"identifiant_operation": self.identifiant_operation,
                "operation": self.operation, "racine": self.racine,
                "tete_avant": self.tete_avant, "tete_apres": self.tete_apres,
                "ok": self.ok, "horodatage": self.horodatage}


class JournalOperationsGit:
    """Mémoire des opérations mutantes déjà exécutées, par identifiant fourni
    par l'appelant. Vit en mémoire du processus (même choix que les
    checkpoints, `git_etat.py`/DEC-0093) — un identifiant ne survit pas à un
    redémarrage d'ARENA, et ce n'est pas son rôle : c'est
    `core/execution/reprise.py` (DEC-0072) qui porte la reprise au niveau
    d'une tâche entière ; ceci protège UNE écriture git contre UNE relance
    (réponse perdue, appelant qui redemande), pas contre un redémarrage.

    Plafonné à `CAPACITE_JOURNAL` entrées (même chiffre que gitgui,
    `AGENT_RESULTS_KEPT`) : au-delà, la plus ancienne est oubliée — un
    identifiant qui revient après des centaines d'autres opérations n'est de
    toute façon plus une vraie relance.
    """

    def __init__(self, capacite: int = CAPACITE_JOURNAL) -> None:
        self._capacite = capacite
        self._resultats: "OrderedDict[str, ResultatOperation]" = OrderedDict()
        self._entrees: List[EntreeJournal] = []

    def dejavu(self, identifiant_operation: Optional[str]) -> Optional[ResultatOperation]:
        """Le résultat déjà obtenu pour cet identifiant, ou `None` — jamais
        ré-exécuté quand il existe déjà (mission §7, cœur de l'idempotence)."""
        if identifiant_operation is None:
            return None
        return self._resultats.get(identifiant_operation)

    def enregistrer(self, resultat: ResultatOperation, racine: Path) -> None:
        """Note l'opération dans le journal, et son résultat sous son
        identifiant si elle en portait un."""
        self._entrees.append(EntreeJournal(
            identifiant_operation=resultat.identifiant_operation, operation=resultat.operation,
            racine=str(racine), tete_avant=resultat.tete_avant, tete_apres=resultat.tete_apres,
            ok=resultat.ok, horodatage=resultat.horodatage))
        if resultat.identifiant_operation is None:
            return
        cle = resultat.identifiant_operation
        if cle in self._resultats:
            del self._resultats[cle]
        self._resultats[cle] = resultat
        while len(self._resultats) > self._capacite:
            self._resultats.popitem(last=False)

    def entrees(self) -> List[Dict[str, Any]]:
        """Le journal complet, pour diagnostic — jamais de secret dedans."""
        return [e.to_dict() for e in self._entrees]


# --- Exécution git bas niveau (réutilise le style de git_etat._executer) --------------

def _executer(racine: Path, arguments: List[str], delai: float) -> "subprocess.CompletedProcess[str]":
    """Lance `git <arguments>` et rend le `CompletedProcess` TEL QUEL — jamais
    d'exception sur un code de sortie non nul : c'est à l'appelant de décider
    ce que « échoué » veut dire pour SON opération (une fusion en conflit
    n'est pas la même chose qu'un dépôt introuvable, et les deux rendent un
    code non nul)."""
    try:
        return subprocess.run(  # noqa: S603 — arguments en liste, jamais shell=True
            ["git", *arguments], cwd=str(racine), capture_output=True,
            text=True, timeout=delai, check=False)
    except FileNotFoundError as erreur:
        raise git_etat.ErreurGit(arguments, None, f"git introuvable : {erreur}") from erreur
    except subprocess.TimeoutExpired as erreur:
        raise git_etat.ErreurGit(arguments, None, f"commande arretee apres {delai:.0f}s") from erreur


def _tete_actuelle(racine: Path, delai: float) -> Optional[str]:
    try:
        return git_etat.lire_etat(racine, delai).tete
    except git_etat.ErreurGit:
        return None


def _resultat_echec(operation: str, message: str, identifiant_operation: Optional[str],
                    tete_avant: Optional[str], sortie: str = "") -> ResultatOperation:
    return ResultatOperation(
        operation=operation, ok=False, message=message,
        identifiant_operation=identifiant_operation, tete_avant=tete_avant, tete_apres=tete_avant,
        type_erreur=classer_erreur(message), sortie=sortie)


def _verifier_precondition(racine: Path, tete_attendue: Optional[str], delai: float) -> Optional[str]:
    """Rend le HEAD actuel. Lève `ErreurPreconditionGit` s'il ne correspond
    pas à `tete_attendue` quand celui-ci est fourni — AVANT toute mutation
    (mission §8/§25/§33)."""
    tete_reelle = _tete_actuelle(racine, delai)
    if tete_attendue is not None and tete_reelle != tete_attendue:
        raise ErreurPreconditionGit(tete_attendue, tete_reelle)
    return tete_reelle


def _executer_idempotent(
        racine: Path, operation: str, identifiant_operation: Optional[str],
        journal: Optional[JournalOperationsGit], tete_attendue: Optional[str], delai: float,
        fonction) -> ResultatOperation:
    """Le squelette commun à toute opération mutante :

    1. déjà vu cet identifiant ? -> son résultat, `doublon=True`, rien ne
       s'exécute une deuxième fois (mission §7/§32) ;
    2. précondition de HEAD, si demandée (mission §8/§25/§33) ;
    3. verrou par DÉPÔT — deux opérations mutantes sur le MÊME dépôt sont
       sérialisées (même principe que `verrous.pour` sur un fichier,
       mission ARENA x TRANS4MERS §20, étendu ici au dépôt entier parce
       qu'une mutation git touche l'index et HEAD, pas un seul fichier) ;
    4. `fonction()` fait le travail réel et rend un `ResultatOperation` ;
    5. le résultat est journalisé (mission §27), sous son identifiant s'il
       en portait un.
    """
    if journal is not None:
        deja = journal.dejavu(identifiant_operation)
        if deja is not None:
            import dataclasses
            return dataclasses.replace(deja, doublon=True)

    with verrous.pour(racine):
        try:
            tete_avant = _verifier_precondition(racine, tete_attendue, delai)
        except ErreurPreconditionGit as erreur:
            resultat = _resultat_echec(operation, str(erreur), identifiant_operation, None)
            resultat.type_erreur = None  # ce n'est pas une erreur git — un refus de precondition
            resultat.donnees = {"tete_attendue": erreur.tete_attendue, "tete_reelle": erreur.tete_reelle}
            if journal is not None:
                journal.enregistrer(resultat, racine)
            return resultat

        resultat = fonction(tete_avant)
        resultat.operation = operation
        resultat.identifiant_operation = identifiant_operation

    if journal is not None:
        journal.enregistrer(resultat, racine)
    return resultat


# --- Stage / unstage -----------------------------------------------------------------

def stager(racine: Path, chemins: List[str], identifiant_operation: Optional[str] = None,
          journal: Optional[JournalOperationsGit] = None, delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git add <chemins>` — indexe exactement les fichiers demandés, jamais
    `-A` implicite (mission §12, « stage only intended files »)."""
    def _faire(tete_avant):
        if not chemins:
            return _resultat_echec("stager", "Aucun chemin a indexer.", identifiant_operation, tete_avant)
        p = _executer(racine, ["add", "--", *chemins], delai)
        if p.returncode != 0:
            return _resultat_echec("stager", p.stderr.strip() or "echec de l'indexation",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        return ResultatOperation("stager", True, f"{len(chemins)} chemin(s) indexe(s).",
                                 tete_avant=tete_avant, tete_apres=tete_avant,
                                 donnees={"chemins": list(chemins)})
    return _executer_idempotent(racine, "stager", identifiant_operation, journal, None, delai, _faire)


def desindexer(racine: Path, chemins: List[str], identifiant_operation: Optional[str] = None,
              journal: Optional[JournalOperationsGit] = None, delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git restore --staged <chemins>` — retire de l'index sans toucher
    l'arbre de travail."""
    def _faire(tete_avant):
        if not chemins:
            return _resultat_echec("desindexer", "Aucun chemin a desindexer.", identifiant_operation, tete_avant)
        p = _executer(racine, ["restore", "--staged", "--", *chemins], delai)
        if p.returncode != 0:
            return _resultat_echec("desindexer", p.stderr.strip() or "echec du desindexage",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        return ResultatOperation("desindexer", True, f"{len(chemins)} chemin(s) desindexe(s).",
                                 tete_avant=tete_avant, tete_apres=tete_avant,
                                 donnees={"chemins": list(chemins)})
    return _executer_idempotent(racine, "desindexer", identifiant_operation, journal, None, delai, _faire)


# --- Commit ----------------------------------------------------------------------------

def commettre(racine: Path, message: str, amend: bool = False,
             tete_attendue: Optional[str] = None, identifiant_operation: Optional[str] = None,
             journal: Optional[JournalOperationsGit] = None,
             delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git commit` — vérifie la postcondition (mission §9/§12) : un nouveau
    HEAD existe réellement et diffère de celui d'avant (sauf `amend`, qui
    remplace le même commit par construction — vérifié autrement : le HEAD
    change quand même de SHA, seul son PARENT reste identique).

    Idempotence à deux niveaux : le journal (`identifiant_operation`) rend le
    même résultat sans rejouer ; ET, même sans identifiant, git lui-même
    refuse un commit dont l'index ne diffère pas de HEAD (`rien a valider,
    l'arbre de travail est propre ») — un « nothing to commit » classé
    `RIEN_A_FAIRE`, jamais un commit vide silencieux.
    """
    def _faire(tete_avant):
        if not message or not message.strip():
            return _resultat_echec("commettre", "Message de commit vide.", identifiant_operation, tete_avant)
        arguments = ["commit", "-m", message]
        if amend:
            arguments.insert(1, "--amend")
        p = _executer(racine, arguments, delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("commettre", texte or "echec du commit",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        tete_apres = _tete_actuelle(racine, delai)
        if tete_apres is None or tete_apres == tete_avant:
            # Postcondition violee : le commit a dit oui mais HEAD n'a pas
            # bouge. Rapporte comme un echec plutot que de supposer.
            return ResultatOperation("commettre", False,
                                     "Le commit a reussi mais HEAD n'a pas change — "
                                     "postcondition violee, verification requise.",
                                     tete_avant=tete_avant, tete_apres=tete_apres,
                                     type_erreur=TypeErreurGit.INCONNUE)
        return ResultatOperation("commettre", True, f"Commit {tete_apres[:12]} cree.",
                                 tete_avant=tete_avant, tete_apres=tete_apres,
                                 sortie=p.stdout, donnees={"amend": amend})
    return _executer_idempotent(racine, "commettre", identifiant_operation, journal, tete_attendue, delai, _faire)


# --- Branches ----------------------------------------------------------------------------

@dataclass(frozen=True)
class InfoBranche:
    nom: str
    est_courante: bool
    amont: Optional[str]
    tete: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"nom": self.nom, "est_courante": self.est_courante,
                "amont": self.amont, "tete": self.tete}


def lister_branches(racine: Path, delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """Les branches locales, structurées — jamais le texte de `git branch` à
    reparser (mission §6, `branch_list`)."""
    p = _executer(racine, ["for-each-ref", "--format=%(refname:short)\t%(HEAD)\t%(upstream:short)\t%(objectname)",
                          "refs/heads/"], delai)
    if p.returncode != 0:
        return _resultat_echec("lister_branches", p.stderr.strip() or "echec de la lecture des branches", None, None)
    branches: List[InfoBranche] = []
    for ligne in p.stdout.splitlines():
        if not ligne:
            continue
        morceaux = ligne.split("\t")
        nom = morceaux[0] if len(morceaux) > 0 else ""
        courante = (morceaux[1] if len(morceaux) > 1 else "") == "*"
        amont = morceaux[2] if len(morceaux) > 2 and morceaux[2] else None
        tete = morceaux[3] if len(morceaux) > 3 and morceaux[3] else None
        branches.append(InfoBranche(nom, courante, amont, tete))
    return ResultatOperation("lister_branches", True, f"{len(branches)} branche(s) locale(s).",
                             donnees={"branches": [b.to_dict() for b in branches]})


def creer_branche(racine: Path, nom: str, depuis: str = "HEAD", basculer: bool = True,
                  identifiant_operation: Optional[str] = None,
                  journal: Optional[JournalOperationsGit] = None,
                  delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git branch <nom> <depuis>`, puis `git checkout <nom>` si `basculer`."""
    def _faire(tete_avant):
        if _nom_ref_invalide(nom):
            return _resultat_echec("creer_branche", f"Nom de branche invalide ou suspect : {nom!r}",
                                   identifiant_operation, tete_avant)
        if _commence_par_option(depuis):
            return _resultat_echec("creer_branche", f"Reference de depart invalide ou suspecte : {depuis!r}",
                                   identifiant_operation, tete_avant)
        p = _executer(racine, ["branch", nom, depuis], delai)
        if p.returncode != 0:
            return _resultat_echec("creer_branche", p.stderr.strip() or "echec de la creation",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        if basculer:
            p2 = _executer(racine, ["checkout", nom], delai)
            if p2.returncode != 0:
                return _resultat_echec("creer_branche",
                                       "Branche creee mais bascule impossible : " +
                                       (p2.stderr.strip() or "erreur inconnue"),
                                       identifiant_operation, tete_avant, sortie=p2.stdout)
        tete_apres = _tete_actuelle(racine, delai)
        return ResultatOperation("creer_branche", True, f"Branche {nom} creee depuis {depuis}.",
                                 tete_avant=tete_avant, tete_apres=tete_apres,
                                 donnees={"nom": nom, "basculee": basculer})
    return _executer_idempotent(racine, "creer_branche", identifiant_operation, journal, None, delai, _faire)


def basculer(racine: Path, cible: str, identifiant_operation: Optional[str] = None,
            journal: Optional[JournalOperationsGit] = None,
            delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git checkout <cible>` — vérifie la postcondition : la branche
    courante (ou HEAD, si détachée) correspond réellement à `cible` après
    coup (mission §9, « BRANCH CHECKOUT -> current branch verified »)."""
    def _faire(tete_avant):
        if _commence_par_option(cible):
            return _resultat_echec("basculer", f"Cible invalide ou suspecte : {cible!r}",
                                   identifiant_operation, tete_avant)
        p = _executer(racine, ["checkout", cible], delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("basculer", texte or "echec de la bascule",
                                   identifiant_operation, tete_avant, sortie=p.stderr)
        etat = git_etat.lire_etat(racine, delai)
        reussi = etat.branche == cible or (etat.tete or "").startswith(cible)
        if not reussi:
            return ResultatOperation("basculer", False,
                                     f"git checkout a reussi mais la branche courante "
                                     f"({etat.branche or etat.tete}) ne correspond pas a {cible!r}.",
                                     tete_avant=tete_avant, tete_apres=etat.tete,
                                     type_erreur=TypeErreurGit.INCONNUE)
        return ResultatOperation("basculer", True, f"Bascule sur {cible}.",
                                 tete_avant=tete_avant, tete_apres=etat.tete,
                                 donnees={"branche": etat.branche, "detachee": etat.detachee})
    return _executer_idempotent(racine, "basculer", identifiant_operation, journal, None, delai, _faire)


# --- Réseau : fetch / pull / push ------------------------------------------------------

def recuperer(racine: Path, distant: str = "origin", identifiant_operation: Optional[str] = None,
             journal: Optional[JournalOperationsGit] = None,
             delai: float = DELAI_RESEAU_PAR_DEFAUT) -> ResultatOperation:
    """`git fetch <distant>` — `GIT_TERMINAL_PROMPT=0` implicite via
    `Atelier`/`os.environ` n'est pas nécessaire ici : `_executer` ne fournit
    aucun stdin, donc git ne peut de toute façon pas lire un mot de passe
    interactif — un blocage devient un timeout rapporté, jamais une attente
    invisible."""
    def _faire(tete_avant):
        if _commence_par_option(distant):
            return _resultat_echec("recuperer", f"Distant invalide ou suspect : {distant!r}",
                                   identifiant_operation, tete_avant)
        p = _executer(racine, ["fetch", distant], delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("recuperer", texte or "echec du fetch",
                                   identifiant_operation, tete_avant, sortie=p.stderr)
        return ResultatOperation("recuperer", True, f"Fetch {distant} termine.",
                                 tete_avant=tete_avant, tete_apres=tete_avant,
                                 sortie=p.stderr, donnees={"distant": distant})
    return _executer_idempotent(racine, "recuperer", identifiant_operation, journal, None, delai, _faire)


def tirer(racine: Path, distant: str = "origin", rebase: bool = False,
         identifiant_operation: Optional[str] = None, journal: Optional[JournalOperationsGit] = None,
         delai: float = DELAI_RESEAU_PAR_DEFAUT) -> ResultatOperation:
    """`git pull [--rebase] <distant>` — un vrai conflit rend `ok=False`,
    `type_erreur=CONFLIT` : jamais poursuivi à l'aveugle (mission §17/§36)."""
    def _faire(tete_avant):
        if _commence_par_option(distant):
            return _resultat_echec("tirer", f"Distant invalide ou suspect : {distant!r}",
                                   identifiant_operation, tete_avant)
        arguments = ["pull"]
        if rebase:
            arguments.append("--rebase")
        arguments.append(distant)
        # La branche courante est passee explicitement : sans amont configure
        # (`git push -u`), un `git pull <distant>` sans refspec refuse de
        # deviner quoi tirer — jamais suppose ici non plus.
        etat_avant = git_etat.lire_etat(racine, delai)
        if etat_avant.branche:
            arguments.append(etat_avant.branche)
        p = _executer(racine, arguments, delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("tirer", texte or "echec du pull",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        tete_apres = _tete_actuelle(racine, delai)
        return ResultatOperation("tirer", True, f"Pull {distant} termine.",
                                 tete_avant=tete_avant, tete_apres=tete_apres,
                                 sortie=p.stdout, donnees={"distant": distant, "rebase": rebase})
    return _executer_idempotent(racine, "tirer", identifiant_operation, journal, None, delai, _faire)


def pousser(racine: Path, distant: str = "origin", branche: Optional[str] = None,
           force_avec_bail: bool = False, identifiant_operation: Optional[str] = None,
           journal: Optional[JournalOperationsGit] = None,
           delai: float = DELAI_RESEAU_PAR_DEFAUT) -> ResultatOperation:
    """`git push <distant> [branche]` — **jamais `--force` nu** (mission §14) :
    `force_avec_bail=True` ajoute `--force-with-lease`, qui refuse tout seul
    si le distant a bougé depuis la dernière fois que ce dépôt l'a vu (donc
    un « autre a poussé entre-temps » reste protégé même en forçant). Un
    rejet non-fast-forward SANS `force_avec_bail` n'est jamais retenté avec
    la force automatiquement — rapporté tel quel, classé `NON_FAST_FORWARD`
    (mission §35, « do not force push automatically »)."""
    def _faire(tete_avant):
        if _commence_par_option(distant):
            return _resultat_echec("pousser", f"Distant invalide ou suspect : {distant!r}",
                                   identifiant_operation, tete_avant)
        if branche and _commence_par_option(branche):
            return _resultat_echec("pousser", f"Branche invalide ou suspecte : {branche!r}",
                                   identifiant_operation, tete_avant)
        arguments = ["push"]
        if force_avec_bail:
            arguments.append("--force-with-lease")
        arguments.append(distant)
        if branche:
            arguments.append(branche)
        p = _executer(racine, arguments, delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("pousser", texte or "echec du push",
                                   identifiant_operation, tete_avant, sortie=p.stderr)
        return ResultatOperation("pousser", True, f"Push {distant} termine.",
                                 tete_avant=tete_avant, tete_apres=tete_avant,
                                 sortie=p.stderr,
                                 donnees={"distant": distant, "branche": branche,
                                         "force_avec_bail": force_avec_bail})
    return _executer_idempotent(racine, "pousser", identifiant_operation, journal, None, delai, _faire)


# --- Fusion / rebase / cherry-pick / revert --------------------------------------------

def fusionner(racine: Path, branche: str, tete_attendue: Optional[str] = None,
             identifiant_operation: Optional[str] = None, journal: Optional[JournalOperationsGit] = None,
             delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git merge <branche>` — un conflit rend `ok=False`, `type_erreur=
    CONFLIT`, et laisse le dépôt en fusion : à l'appelant de lire l'état
    (`git_etat.lire_etat` -> `conflits`, `operation=FUSION`), résoudre, puis
    `continuer_operation()`."""
    def _faire(tete_avant):
        if _commence_par_option(branche):
            return _resultat_echec("fusionner", f"Branche invalide ou suspecte : {branche!r}",
                                   identifiant_operation, tete_avant)
        p = _executer(racine, ["merge", "--no-edit", branche], delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("fusionner", texte or "echec de la fusion",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        tete_apres = _tete_actuelle(racine, delai)
        return ResultatOperation("fusionner", True, f"Fusion de {branche} terminee.",
                                 tete_avant=tete_avant, tete_apres=tete_apres,
                                 sortie=p.stdout, donnees={"branche": branche})
    return _executer_idempotent(racine, "fusionner", identifiant_operation, journal, tete_attendue, delai, _faire)


def rebaser(racine: Path, sur: str, tete_attendue: Optional[str] = None,
           identifiant_operation: Optional[str] = None, journal: Optional[JournalOperationsGit] = None,
           delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git rebase <sur>` — jamais sur une branche protégée par défaut :
    c'est à l'appelant de consulter `EtatGit.branche_protegee()` d'abord
    (champ informatif, DEC-0093) ; ce module ne refuse rien lui-même
    (DEC-0038 non re-litigé), il donne l'information pour décider."""
    def _faire(tete_avant):
        if _commence_par_option(sur):
            return _resultat_echec("rebaser", f"Reference invalide ou suspecte : {sur!r}",
                                   identifiant_operation, tete_avant)
        p = _executer(racine, ["rebase", sur], delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("rebaser", texte or "echec du rebase",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        tete_apres = _tete_actuelle(racine, delai)
        return ResultatOperation("rebaser", True, f"Rebase sur {sur} termine.",
                                 tete_avant=tete_avant, tete_apres=tete_apres,
                                 sortie=p.stdout, donnees={"sur": sur})
    return _executer_idempotent(racine, "rebaser", identifiant_operation, journal, tete_attendue, delai, _faire)


def cherry_pick(racine: Path, commit: str, tete_attendue: Optional[str] = None,
                identifiant_operation: Optional[str] = None, journal: Optional[JournalOperationsGit] = None,
                delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git cherry-pick <commit>`."""
    def _faire(tete_avant):
        if _commence_par_option(commit):
            return _resultat_echec("cherry_pick", f"Commit invalide ou suspect : {commit!r}",
                                   identifiant_operation, tete_avant)
        p = _executer(racine, ["cherry-pick", commit], delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("cherry_pick", texte or "echec du cherry-pick",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        tete_apres = _tete_actuelle(racine, delai)
        return ResultatOperation("cherry_pick", True, f"Cherry-pick de {commit} termine.",
                                 tete_avant=tete_avant, tete_apres=tete_apres,
                                 sortie=p.stdout, donnees={"commit": commit})
    return _executer_idempotent(racine, "cherry_pick", identifiant_operation, journal, tete_attendue, delai, _faire)


def annuler_commit(racine: Path, commit: str, tete_attendue: Optional[str] = None,
                   identifiant_operation: Optional[str] = None, journal: Optional[JournalOperationsGit] = None,
                   delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git revert --no-edit <commit>` (jamais `reset` — un revert AJOUTE un
    commit qui annule, il ne réécrit rien)."""
    def _faire(tete_avant):
        if _commence_par_option(commit):
            return _resultat_echec("annuler_commit", f"Commit invalide ou suspect : {commit!r}",
                                   identifiant_operation, tete_avant)
        p = _executer(racine, ["revert", "--no-edit", commit], delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("annuler_commit", texte or "echec du revert",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        tete_apres = _tete_actuelle(racine, delai)
        return ResultatOperation("annuler_commit", True, f"Revert de {commit} termine.",
                                 tete_avant=tete_avant, tete_apres=tete_apres,
                                 sortie=p.stdout, donnees={"commit": commit})
    return _executer_idempotent(racine, "annuler_commit", identifiant_operation, journal, tete_attendue, delai, _faire)


# --- Tag ---------------------------------------------------------------------------------

def creer_tag(racine: Path, nom: str, cible: str = "HEAD", message: Optional[str] = None,
             identifiant_operation: Optional[str] = None, journal: Optional[JournalOperationsGit] = None,
             delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git tag [-a -m <message>] <nom> <cible>`."""
    def _faire(tete_avant):
        if _nom_ref_invalide(nom):
            return _resultat_echec("creer_tag", f"Nom de tag invalide ou suspect : {nom!r}",
                                   identifiant_operation, tete_avant)
        if _commence_par_option(cible):
            return _resultat_echec("creer_tag", f"Cible invalide ou suspecte : {cible!r}",
                                   identifiant_operation, tete_avant)
        arguments = ["tag"]
        if message:
            arguments += ["-a", "-m", message]
        arguments += [nom, cible]
        p = _executer(racine, arguments, delai)
        if p.returncode != 0:
            return _resultat_echec("creer_tag", p.stderr.strip() or "echec de la creation du tag",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        return ResultatOperation("creer_tag", True, f"Tag {nom} cree sur {cible}.",
                                 tete_avant=tete_avant, tete_apres=tete_avant,
                                 donnees={"nom": nom, "cible": cible})
    return _executer_idempotent(racine, "creer_tag", identifiant_operation, journal, None, delai, _faire)


# --- Stash -------------------------------------------------------------------------------

def remiser(racine: Path, message: Optional[str] = None, inclure_non_suivis: bool = False,
           identifiant_operation: Optional[str] = None, journal: Optional[JournalOperationsGit] = None,
           delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git stash push [-u] [-m <message>]`."""
    def _faire(tete_avant):
        arguments = ["stash", "push"]
        if inclure_non_suivis:
            arguments.append("-u")
        if message:
            arguments += ["-m", message]
        p = _executer(racine, arguments, delai)
        if p.returncode != 0:
            return _resultat_echec("remiser", p.stderr.strip() or "echec de la remise",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        return ResultatOperation("remiser", True, p.stdout.strip() or "Remise creee.",
                                 tete_avant=tete_avant, tete_apres=tete_avant, sortie=p.stdout)
    return _executer_idempotent(racine, "remiser", identifiant_operation, journal, None, delai, _faire)


def appliquer_remise(racine: Path, index: int = 0, garder: bool = False,
                     identifiant_operation: Optional[str] = None, journal: Optional[JournalOperationsGit] = None,
                     delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git stash apply stash@{index}` (`garder=True`) ou `git stash pop
    stash@{index}` (par defaut — la remise est retiree une fois appliquee)."""
    def _faire(tete_avant):
        sous_commande = "apply" if garder else "pop"
        p = _executer(racine, ["stash", sous_commande, f"stash@{{{index}}}"], delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("appliquer_remise", texte or "echec de l'application",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        return ResultatOperation("appliquer_remise", True, f"Remise {index} appliquee ({sous_commande}).",
                                 tete_avant=tete_avant, tete_apres=tete_avant, sortie=p.stdout)
    return _executer_idempotent(racine, "appliquer_remise", identifiant_operation, journal, None, delai, _faire)


# --- Conflits : lecture à trois voies ---------------------------------------------------

@dataclass(frozen=True)
class VueConflit:
    """Les trois côtés d'un conflit — mission §17 : « OURS, BASE, THEIRS,
    RESULT ». `resultat` est le contenu actuel du fichier dans l'arbre de
    travail (avec les marqueurs `<<<<<<<`), ce que l'appelant doit réécrire
    avant de `stager()` puis `continuer_operation()`."""

    chemin: str
    notre_version: Optional[str]
    version_de_base: Optional[str]
    leur_version: Optional[str]
    resultat_actuel: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"chemin": self.chemin, "notre_version": self.notre_version,
                "version_de_base": self.version_de_base, "leur_version": self.leur_version,
                "resultat_actuel": self.resultat_actuel}


def _blob_stage(racine: Path, etage: int, chemin: str, delai: float) -> Optional[str]:
    p = _executer(racine, ["show", f":{etage}:{chemin}"], delai)
    return p.stdout if p.returncode == 0 else None


def lire_conflit(racine: Path, chemin: str, delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """Les trois côtés d'un fichier en conflit — jamais une résolution
    automatique « ours »/« theirs » choisie ici (mission §17, « do not
    merely choose ours/theirs automatically »). L'appelant lit les trois
    côtés, comprend le code autour, propose une résolution, puis l'écrit
    lui-même (`Atelier.ecrire`/`remplacer`) avant de `stager()`."""
    base = _blob_stage(racine, 1, chemin, delai)
    ours = _blob_stage(racine, 2, chemin, delai)
    theirs = _blob_stage(racine, 3, chemin, delai)
    try:
        actuel = (racine / chemin).read_text(encoding="utf-8", errors="replace")
    except OSError:
        actuel = None
    if ours is None and theirs is None and base is None:
        return ResultatOperation("lire_conflit", False, f"{chemin} n'est pas en conflit "
                                 "(aucun etage 1/2/3 dans l'index).")
    vue = VueConflit(chemin, ours, base, theirs, actuel)
    return ResultatOperation("lire_conflit", True, f"Conflit lu sur {chemin}.", donnees=vue.to_dict())


# --- Continuer / abandonner (auto-détection de l'opération en cours) ------------------

_SOUS_COMMANDE_PAR_OPERATION = {
    git_etat.EtatOperation.FUSION: "merge",
    git_etat.EtatOperation.REBASE: "rebase",
    git_etat.EtatOperation.CHERRY_PICK: "cherry-pick",
    git_etat.EtatOperation.REVERT: "revert",
}


def continuer_operation(racine: Path, identifiant_operation: Optional[str] = None,
                        journal: Optional[JournalOperationsGit] = None,
                        delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git <fusion|rebase|cherry-pick|revert> --continue` — détecte
    laquelle est en cours via `EtatOperation` (jamais devinée), refuse
    proprement si aucune ne l'est (mission §18, « know how to recover »)."""
    def _faire(tete_avant):
        etat = git_etat.lire_etat(racine, delai)
        sous = _SOUS_COMMANDE_PAR_OPERATION.get(etat.operation)
        if sous is None:
            return _resultat_echec("continuer_operation",
                                   "Aucune operation (fusion/rebase/cherry-pick/revert) en cours a continuer.",
                                   identifiant_operation, tete_avant)
        p = _executer(racine, [sous, "--continue"], delai)
        if p.returncode != 0:
            texte = (p.stdout + "\n" + p.stderr).strip()
            return _resultat_echec("continuer_operation", texte or f"echec de {sous} --continue",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        tete_apres = _tete_actuelle(racine, delai)
        return ResultatOperation("continuer_operation", True, f"{sous} continue avec succes.",
                                 tete_avant=tete_avant, tete_apres=tete_apres,
                                 sortie=p.stdout, donnees={"operation": sous})
    return _executer_idempotent(racine, "continuer_operation", identifiant_operation, journal, None, delai, _faire)


def abandonner_operation(racine: Path, identifiant_operation: Optional[str] = None,
                         journal: Optional[JournalOperationsGit] = None,
                         delai: float = DELAI_PAR_DEFAUT) -> ResultatOperation:
    """`git <fusion|rebase|cherry-pick|revert> --abort` — même détection.
    Toujours sûr par construction : `--abort` est l'opération de secours de
    git lui-même, jamais un `reset --hard` maison qui pourrait emporter
    autre chose (mission §37, « verify repository returns to a valid
    expected state »)."""
    def _faire(tete_avant):
        etat = git_etat.lire_etat(racine, delai)
        sous = _SOUS_COMMANDE_PAR_OPERATION.get(etat.operation)
        if sous is None:
            return _resultat_echec("abandonner_operation",
                                   "Aucune operation (fusion/rebase/cherry-pick/revert) en cours a abandonner.",
                                   identifiant_operation, tete_avant)
        p = _executer(racine, [sous, "--abort"], delai)
        if p.returncode != 0:
            return _resultat_echec("abandonner_operation", p.stderr.strip() or f"echec de {sous} --abort",
                                   identifiant_operation, tete_avant, sortie=p.stdout)
        tete_apres = _tete_actuelle(racine, delai)
        etat_apres = git_etat.lire_etat(racine, delai)
        if etat_apres.operation != git_etat.EtatOperation.PROPRE:
            return ResultatOperation("abandonner_operation", False,
                                     f"{sous} --abort a reussi mais une operation "
                                     f"({etat_apres.operation.value}) reste en cours.",
                                     tete_avant=tete_avant, tete_apres=tete_apres,
                                     type_erreur=TypeErreurGit.INCONNUE)
        return ResultatOperation("abandonner_operation", True, f"{sous} abandonne, depot revenu propre.",
                                 tete_avant=tete_avant, tete_apres=tete_apres,
                                 sortie=p.stdout, donnees={"operation": sous})
    return _executer_idempotent(racine, "abandonner_operation", identifiant_operation, journal, None, delai, _faire)
