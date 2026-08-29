"""Trois constats réels, jamais une sécurité ou une architecture inventée.

**Provenance** : demandé le 29/08/2026, à partir de `OpenAutoCoder/
live-swe-agent` (MIT) — audité, pas seulement lu en README. Le dépôt ne
contient AUCUN code d'agent : `LICENSE`, `README.md`, un dossier `config/`
avec un unique fichier YAML. Sa « self-evolution » est une INSTRUCTION dans
un prompt système (« you can create your own tools in Python »), exécutée
par un moteur tiers non vendu ici (`mini-swe-agent`) — que ce dépôt ne fait
que configurer. Il n'y a rien à intégrer comme code ; `docs/DECISIONS.md`
(DEC-0014) explique pourquoi rien n'est copié, et pourquoi la promesse
d'une garde autonome permanente qui modifie ARENA seule n'est pas tenue ici.

**Ce module rend ce qu'il peut prouver, rien de plus** : trois catégories,
chacune sur un outil réel déjà dans ce dépôt — jamais une « sécurité »
ou une « architecture » scannée qui n'existerait que dans le nom du champ.

1. **BUG** — `pytest -q`, les tests qui échouent réellement.
2. **QUALITE_CODE** — `ruff check --output-format=json`, ce que le linter
   trouve réellement.
3. **CODE_MORT** — `scripts/orphelins.py`, les modules que le chemin de
   réponse n'atteint pas — réutilisé, pas réécrit.

Une analyse de sécurité ou de performance dignes de ce nom n'existe pas
encore : `SUGGESTION — NON IMPLÉMENTÉE` (DEC-0014), plutôt qu'un champ qui
rendrait toujours `[]` et se ferait passer pour une garantie.
"""
import hashlib
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

logger = logging.getLogger("usman.guardian.diagnostics")

RACINE = Path(__file__).resolve().parents[2]

CATEGORIE_BUG = "BUG"
CATEGORIE_QUALITE = "QUALITE_CODE"
CATEGORIE_CODE_MORT = "CODE_MORT"

#: Gravité par defaut par categorie — un depart honnete, pas un classement
#: fin par regle : ce module ne pretend pas savoir qu'un test casse plus ou
#: moins qu'un autre sans le lire.
GRAVITE_PAR_CATEGORIE = {CATEGORIE_BUG: "P2", CATEGORIE_QUALITE: "P5", CATEGORIE_CODE_MORT: "P6"}

DELAI_SECONDES = 300.0

#: Le format qu'appelle chaque diagnostic : (commande) -> (code, stdout, stderr).
Executeur = Callable[[List[str]], "SortieCommande"]


@dataclass(frozen=True)
class SortieCommande:
    code: int
    stdout: str
    stderr: str


def executer_reel(commande: List[str]) -> SortieCommande:
    """L'exécuteur par défaut : un vrai sous-processus, jamais simulé."""
    try:
        resultat = subprocess.run(
            commande, cwd=str(RACINE), capture_output=True, text=True,
            timeout=DELAI_SECONDES,
        )
        return SortieCommande(resultat.returncode, resultat.stdout, resultat.stderr)
    except subprocess.TimeoutExpired as erreur:
        return SortieCommande(-1, "", f"delai depasse ({DELAI_SECONDES:g}s) : {erreur}")
    except OSError as erreur:
        return SortieCommande(-1, "", f"{type(erreur).__name__}: {erreur}")


@dataclass(frozen=True)
class Constat:
    """Une chose trouvée, jamais devinée — avec de quoi la revérifier."""

    categorie: str
    gravite: str
    description: str
    fichier: str = ""
    preuve: str = ""

    @property
    def empreinte(self) -> str:
        """Identité stable pour la déduplication entre deux cycles — pas
        l'horodatage, pas le texte de la preuve (qui peut varier de peu)."""
        brut = f"{self.categorie}|{self.fichier}|{self.description}"
        return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]


#: La ligne du recapitulatif final — mesuree sur ce pytest, elle ne porte QUE
#: le noeud, jamais de raison a cote (contrairement a ce qu'un premier essai
#: supposait sans verifier — corrige apres l'avoir vu echouer en vrai).
_LIGNE_ECHEC = re.compile(r"^FAILED (?P<noeud>\S+)\s*$", re.MULTILINE)

#: La trace courte qu'ecrit `--tb=line`, une ligne par echec : « fichier:ligne:
#: Exception: message ». Associee au constat par fichier — assez pour une
#: preuve lisible, sans pretendre appairer chaque echec au caractere pres
#: quand plusieurs tests du meme fichier echouent.
_LIGNE_TRACE = re.compile(r"^(?P<fichier>\S+\.py):(?P<ligne>\d+): (?P<detail>.+)$", re.MULTILINE)


def diagnostiquer_bugs(executer: Executeur = executer_reel) -> List[Constat]:
    """`pytest -q --tb=line` réel — un `Constat` par test qui échoue pour de vrai."""
    sortie = executer([sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"])

    traces_par_fichier = {}
    for trace in _LIGNE_TRACE.finditer(sortie.stdout):
        # pytest ecrit ce chemin absolu ; le noeud du recapitulatif est
        # relatif a la racine — les deux doivent converger pour s'apparier.
        try:
            chemin_relatif = str(Path(trace.group("fichier")).resolve().relative_to(RACINE))
        except (ValueError, OSError):
            chemin_relatif = trace.group("fichier")
        traces_par_fichier.setdefault(
            chemin_relatif,
            f"{trace.group('fichier')}:{trace.group('ligne')}: {trace.group('detail')}")

    constats = []
    for correspondance in _LIGNE_ECHEC.finditer(sortie.stdout):
        noeud = correspondance.group("noeud")
        fichier = noeud.split("::")[0]
        constats.append(Constat(
            categorie=CATEGORIE_BUG, gravite=GRAVITE_PAR_CATEGORIE[CATEGORIE_BUG],
            description=f"test en echec : {noeud}",
            fichier=fichier,
            preuve=traces_par_fichier.get(fichier, "(trace non capturee)"),
        ))
    return constats


def diagnostiquer_qualite(executer: Executeur = executer_reel) -> List[Constat]:
    """`ruff check --output-format=json` réel — un `Constat` par violation."""
    sortie = executer([sys.executable, "-m", "ruff", "check", ".",
                       "--output-format=json"])
    try:
        violations = json.loads(sortie.stdout or "[]")
    except json.JSONDecodeError:
        logger.error("Sortie ruff illisible : %s", sortie.stdout[:200])
        return []
    constats = []
    for v in violations:
        chemin = v.get("filename", "")
        try:
            chemin = str(Path(chemin).resolve().relative_to(RACINE))
        except (ValueError, OSError):
            pass
        code = (v.get("code") or "?")
        constats.append(Constat(
            categorie=CATEGORIE_QUALITE, gravite=GRAVITE_PAR_CATEGORIE[CATEGORIE_QUALITE],
            description=f"{code} : {v.get('message', '')}".strip(),
            fichier=f"{chemin}:{(v.get('location') or {}).get('row', '?')}",
            preuve=json.dumps(v.get("location") or {}),
        ))
    return constats


def diagnostiquer_code_mort() -> List[Constat]:
    """Reutilise `scripts/orphelins.py` en process — pas de sous-processus,
    pas de logique de reperage reecrite une seconde fois."""
    chemin_scripts = RACINE / "scripts"
    if str(chemin_scripts) not in sys.path:
        sys.path.insert(0, str(chemin_scripts))
    from orphelins import orphelins_reels  # import tardif : evite un cycle au chargement du paquet

    return [
        Constat(
            categorie=CATEGORIE_CODE_MORT, gravite=GRAVITE_PAR_CATEGORIE[CATEGORIE_CODE_MORT],
            description=f"module non atteint par le chemin de reponse : {module}",
            fichier=module.replace(".", "/") + ".py",
        )
        for module in sorted(orphelins_reels())
    ]


def diagnostiquer_tout(executer: Executeur = executer_reel) -> List[Constat]:
    """Les trois catégories réelles, dans l'ordre le moins coûteux d'abord."""
    return [
        *diagnostiquer_code_mort(),
        *diagnostiquer_qualite(executer),
        *diagnostiquer_bugs(executer),
    ]
