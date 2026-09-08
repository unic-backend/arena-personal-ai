"""La verification FORMELLE d'ARENA : Lean tranche, jamais le modele.

**Ce qu'ARENA savait deja faire, verifie avant d'ecrire une ligne** :
`core/reasoning/reasoning_engine.py` planifie, execute du Python (sympy,
numpy) dans le bac a sable, puis synthetise. C'est du **calcul**, et il
est reel. Ce qu'il ne fait pas — ce qu'aucun module d'ARENA ne faisait —
c'est **prouver**. Un modele qui ecrit « demonstration : CQFD » produit
une phrase, pas une garantie, et rien ne pouvait le contredire.

Ce connecteur ne remplace donc rien. Il ajoute une couche au-dessus :

    raisonnement ordinaire   -> le modele
    calcul exact             -> bac a sable Python (sympy) — inchange
    PREUVE                   -> Lean, ici

**La technologie reprise a `anthropics/fermats-last-theorem`** (Apache-2.0,
etudie le 07/09/2026) n'est PAS la preuve de Fermat, qui n'a aucun usage
ici et exigerait Mathlib et des heures de compilation. C'est une
discipline, tenue dans son `FinalCheck.lean` en trois lignes :

    #print axioms fermat_last_theorem
    -- attendu : [propext, Classical.choice, Quot.sound]

**Pourquoi ca compte, mesure ici le 07/09/2026** : une preuve trouee
compile SANS ERREUR.

    theorem avec_trou (n : Nat) : n + 0 = n := by sorry
    -> code de sortie 0, et « depends on axioms: [sorryAx] »

Juger sur le code de sortie aurait donc declare VERIFIEE une preuve vide —
exactement le `SUCCESS` sans preuve que `core/actions/resultat.py` refuse
de construire. **Le verdict de ce module ne vient jamais du code de sortie
seul** : il vient de la liste des axiomes.

**Trois regles :**

1. **Lean tranche, pas le modele.** Le verdict sort du binaire, jamais
   d'une phrase. Lean absent -> `NON_CONFIGURE`, jamais une supposition.
2. **Compiler n'est pas prouver.** Un axiome hors de la base de confiance
   (`sorryAx` en tete) rend un REJET, meme sur un code de sortie 0.
3. **Rien ne tourne sans borne.** Delai dur, groupe de processus tue en
   entier, source plafonnee — une preuve mal formee ne lance pas un
   processus qui reste.
"""
from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.formel")

#: Ou le toolchain est installe quand il l'est. Hors du depot (2,9 Go), comme
#: tout moteur externe (`tests/test_moteurs_externes_restent_dehors.py`).
DOSSIER_LEAN = Path("tools") / "formel" / "lean"

#: Ou les preuves verifiees sont gardees. Un artefact doit se retrouver.
DOSSIER_PREUVES = Path("data") / "preuves"

#: Verifier une preuve courte prend moins d'une seconde ; une preuve qui
#: cherche peut boucler. La borne protege la machine, elle n'est pas un
#: budget d'attente normal.
DELAI_SECONDES = 120.0

#: Au-dela, ce n'est plus une preuve a verifier a la volee.
TAILLE_MAX_SOURCE = 200_000

#: Les trois axiomes de la logique de Lean. Tout ce qui sort de cet ensemble
#: fait la difference entre « prouve » et « admis » — `sorryAx` en premier.
#: Repris de `FinalCheck.lean` du depot Fermat (Apache-2.0), qui epingle
#: exactement cette liste pour son theoreme final.
AXIOMES_DE_CONFIANCE = frozenset({"propext", "Classical.choice", "Quot.sound"})

#: Ce qui, dans une source Lean, s'execute A LA COMPILATION et peut sortir du
#: role de verificateur (lancer un processus, lire le disque, ouvrir le
#: reseau). **C'est une barriere, pas un bac a sable** : Lean est un langage
#: a metaprogrammation, et cette liste ne pretend pas etre exhaustive. Elle
#: arrete le cas direct ; le vrai controle reste la permission
#: `EXECUTE_COMMANDS`, eteinte par defaut.
CONSTRUCTIONS_INTERDITES = (
    "IO.Process", "IO.FS", "System.FilePath", "IO.getEnv",
    "unsafe ", "implemented_by", "extern", "opaque unsafe",
)

CE_QUI_MANQUE = (
    "Lean n'est pas installe. C'est un moteur separe (Apache-2.0) qu'ARENA "
    "appelle, jamais un module d'ARENA : voir docs/COMMANDES_PC.md."
)

#: Ce que Lean dit, et ce que ca veut dire pour l'appelant. L'ordre compte :
#: le premier motif qui reconnait gagne.
FAMILLES_D_ERREUR = (
    ("unknown identifier", "identifiant inconnu"),
    ("unknown constant", "identifiant inconnu"),
    ("unsolved goals", "but non demontre"),
    ("type mismatch", "type incompatible"),
    # Le cas le plus frequent d'une preuve FAUSSE : la tactique ne conclut pas
    # parce que l'enonce ne tient pas. Mesure du 07/09/2026 sur
    # `2 + 2 = 5 := by rfl` — sans cette ligne, l'echec sortait sans famille.
    ("not definitionally equal", "egalite non verifiable par calcul"),
    ("failed to synthesize", "instance manquante"),
    ("unexpected token", "erreur de syntaxe"),
    ("unexpected identifier", "erreur de syntaxe"),
    ("unknown module", "import manquant"),
    ("object file", "import manquant"),
    ("maximum recursion depth", "preuve trop profonde"),
    ("deterministic timeout", "budget de calcul depasse"),
)

_AXIOMES = re.compile(r"depends on axioms:\s*\[([^\]]*)\]")
_SANS_AXIOME = re.compile(r"does not depend on any axioms")
_NOM_THEOREME = re.compile(r"^\s*(?:private\s+|protected\s+|noncomputable\s+)*"
                           r"(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_'.]*)",
                           re.MULTILINE)


class LeanAbsent(RuntimeError):
    """Le binaire n'est pas la. On le dit, on ne le simule pas."""


def chemin_de_lean() -> Optional[Path]:
    """Le binaire `lean`, ou `None`. Jamais devine ailleurs qu'ici.

    `LEAN_BIN` prime — c'est la seule facon pour le proprietaire de pointer
    une installation faite ailleurs (elan, paquet systeme) sans toucher au
    code. Sinon, l'emplacement conventionnel de ce depot.
    """
    declare = os.environ.get("LEAN_BIN", "").strip()
    if declare:
        chemin = Path(declare)
        return chemin if chemin.is_file() else None
    depuis_le_depot = Path(__file__).resolve().parent.parent.parent / DOSSIER_LEAN / "bin" / "lean"
    return depuis_le_depot if depuis_le_depot.is_file() else None


def nom_du_theoreme(source: str) -> Optional[str]:
    """Le nom du PREMIER theoreme declare, pour savoir quoi interroger.

    Sans nom, aucun `#print axioms` n'est possible, donc aucune preuve que la
    demonstration est complete — et le module refuse plutot que de rendre un
    verdict qu'il ne peut pas fonder.
    """
    trouve = _NOM_THEOREME.search(source or "")
    return trouve.group(1) if trouve else None


def axiomes_declares(sortie: str) -> Optional[List[str]]:
    """Les axiomes que Lean rapporte, ou `None` s'il n'a rien dit.

    `None` n'est PAS une liste vide : « Lean ne s'est pas prononce » et
    « la preuve ne depend d'aucun axiome » sont deux constats differents, et
    les confondre declarerait verifiee une preuve jamais interrogee.
    """
    if _SANS_AXIOME.search(sortie or ""):
        return []
    trouve = _AXIOMES.search(sortie or "")
    if not trouve:
        return None
    return [a.strip() for a in trouve.group(1).split(",") if a.strip()]


def famille_d_erreur(diagnostics: str) -> Optional[str]:
    """Ce que l'erreur de Lean veut dire, en francais, pour l'appelant."""
    minuscule = (diagnostics or "").lower()
    for motif, famille in FAMILLES_D_ERREUR:
        if motif in minuscule:
            return famille
    return None


class ConnecteurLeanFormel(Connecteur):
    """Verifier une preuve Lean, et ne jamais l'affirmer sans l'avoir lancee."""

    service = "lean_formel"
    nom = "formel"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else DOSSIER_PREUVES

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "verifier": Capacite(
                nom="verifier", action="verifier",
                description=("Vérifie une preuve Lean : la compile réellement et "
                             "contrôle qu'elle ne repose sur aucun axiome ajouté."),
                ecriture=False),
        }

    # --- Sante ------------------------------------------------------------------

    def sonder(self) -> Sante:
        """Lean repond-il ? On lui demande sa version, on ne la suppose pas."""
        binaire = chemin_de_lean()
        if binaire is None:
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="Lean introuvable.",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        try:
            sortie = subprocess.run([str(binaire), "--version"],
                                    capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as erreur:
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message=f"Lean n'a pas repondu ({type(erreur).__name__}).",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        if sortie.returncode != 0:
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="Lean a repondu une erreur a `--version`.",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        return Sante(etat=EtatSante.OPERATIONNEL,
                     message=(sortie.stdout or "").strip() or "Lean repond.",
                     mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : un verificateur local ne demande aucun identifiant."""
        return True

    # --- Le coeur ---------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        return self._verifier(**parametres)

    def _lancer_lean(self, binaire: Path, fichier: Path,
                     delai: float) -> Dict[str, Any]:
        """Lance Lean sur un fichier, borne, et tue le GROUPE en cas de delai.

        Tuer le seul processus de tete laisserait ses enfants actifs alors
        qu'on a deja rapporte « arretee » — meme raison que dans
        `tools/atelier/atelier.py`, et meme forme.
        """
        depart = time.monotonic()
        try:
            processus = subprocess.Popen(  # noqa: S603 — binaire resolu, jamais un shell
                [str(binaire), fichier.name],
                cwd=str(fichier.parent), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=(os.name == "posix"))
        except (OSError, subprocess.SubprocessError) as erreur:
            return {"lance": False, "erreur": f"{type(erreur).__name__}: {erreur}"}

        try:
            sortie, erreur_std = processus.communicate(timeout=delai)
            arrete = False
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(processus.pid, signal.SIGKILL)
            else:
                processus.kill()
            sortie, erreur_std = processus.communicate()
            arrete = True

        return {
            "lance": True, "arrete": arrete,
            "code": processus.returncode,
            "sortie": sortie or "", "erreur_std": erreur_std or "",
            "duree_ms": int((time.monotonic() - depart) * 1000),
        }

    def _verifier(self, source: str = "", theoreme: str = "",
                  delai: float = DELAI_SECONDES, **_: Any) -> ResultatAction:
        propre = (source or "").strip()
        if not propre:
            return echec(action="verifier", cible=self.nom,
                         message="Aucune source Lean : rien a verifier.")
        if len(propre) > TAILLE_MAX_SOURCE:
            return echec(action="verifier", cible=self.nom,
                         message=f"Source trop longue ({len(propre)} caracteres, "
                                 f"plafond {TAILLE_MAX_SOURCE}).")

        interdit = [c for c in CONSTRUCTIONS_INTERDITES if c in propre]
        if interdit:
            # Une preuve n'a aucun besoin de lancer un processus ni de lire le
            # disque. Ce qui en demande n'est pas une preuve : on ne le lance pas.
            return echec(
                action="verifier", cible=self.nom,
                message=("Source refusee : elle contient de quoi s'executer a la "
                         f"compilation ({', '.join(interdit)}). Une preuve n'en a "
                         "pas besoin."),
                refus="execution_a_la_compilation", constructions=interdit)

        nom = (theoreme or "").strip() or nom_du_theoreme(propre)
        if not nom:
            return echec(
                action="verifier", cible=self.nom,
                message=("Aucun `theorem` ou `lemma` nomme dans cette source : "
                         "sans nom, ses axiomes ne peuvent pas etre interroges, "
                         "et rien ne prouverait que la demonstration est complete."))

        binaire = chemin_de_lean()
        if binaire is None:
            return non_configure(action="verifier", cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE)

        # `#print axioms` est AJOUTE par ARENA, jamais attendu de l'appelant :
        # c'est le controle du module, il ne doit pas dependre de la bonne
        # volonte de celui qui envoie la preuve.
        complet = f"{propre}\n\n#print axioms {nom}\n"

        with tempfile.TemporaryDirectory(prefix="arena-lean-") as travail:
            fichier = Path(travail) / "Preuve.lean"
            fichier.write_text(complet, encoding="utf-8")
            mesure = self._lancer_lean(binaire, fichier, delai)

        if not mesure["lance"]:
            return echec(action="verifier", cible=self.nom,
                         message=f"Lean n'a pas pu etre lance : {mesure['erreur']}")

        diagnostics = (mesure["sortie"] + "\n" + mesure["erreur_std"]).strip()

        if mesure["arrete"]:
            return echec(
                action="verifier", cible=self.nom,
                message=f"Verification arretee apres {delai:.0f} s : la preuve "
                        "n'a pas abouti dans le temps accorde.",
                verdict="DELAI", theoreme=nom, duree_ms=mesure["duree_ms"],
                famille="delai depasse", diagnostics=diagnostics[:2000])

        if mesure["code"] != 0:
            return echec(
                action="verifier", cible=self.nom,
                message=f"Preuve REJETEE par Lean : {famille_d_erreur(diagnostics) or 'erreur de compilation'}.",
                verdict="REJETE", theoreme=nom, code=mesure["code"],
                duree_ms=mesure["duree_ms"],
                famille=famille_d_erreur(diagnostics),
                diagnostics=diagnostics[:2000])

        axiomes = axiomes_declares(diagnostics)
        if axiomes is None:
            # Lean a compile mais ne s'est pas prononce sur les axiomes : on ne
            # comble pas ce silence par une supposition favorable.
            return echec(
                action="verifier", cible=self.nom,
                message=("Lean a compile mais n'a rapporte aucun axiome pour "
                         f"« {nom} » : rien ne prouve que la demonstration est "
                         "complete."),
                verdict="INDETERMINE", theoreme=nom, duree_ms=mesure["duree_ms"],
                diagnostics=diagnostics[:2000])

        ajoutes = sorted(set(axiomes) - AXIOMES_DE_CONFIANCE)
        if ajoutes:
            # C'est ici que se joue tout le module : le code de sortie vaut 0.
            troue = "sorryAx" in ajoutes
            return echec(
                action="verifier", cible=self.nom,
                message=("Preuve REJETEE : elle compile, mais repose sur "
                         + ("un trou (`sorry`)" if troue else
                            f"des axiomes ajoutes ({', '.join(ajoutes)})")
                         + " — compiler n'est pas prouver."),
                verdict="REJETE", theoreme=nom, axiomes=axiomes,
                axiomes_ajoutes=ajoutes, troue=troue,
                duree_ms=mesure["duree_ms"], code=mesure["code"],
                famille="preuve incomplete", diagnostics=diagnostics[:2000])

        # Verifiee : Lean a compile, et les axiomes sont ceux de sa logique.
        self.dossier.mkdir(parents=True, exist_ok=True)
        artefact = self.dossier / f"preuve-{uuid.uuid4().hex[:8]}.lean"
        artefact.write_text(complet, encoding="utf-8")

        return succes(
            action="verifier", cible=self.nom,
            message=(f"Preuve VERIFIEE par Lean : « {nom} » ne repose que sur "
                     f"{', '.join(axiomes) if axiomes else 'aucun axiome'}."),
            preuve=str(artefact),
            verdict="VERIFIE", theoreme=nom, axiomes=axiomes,
            axiomes_ajoutes=[], troue=False,
            duree_ms=mesure["duree_ms"], code=mesure["code"])
