"""Diagnostics réels du dépôt, avec échec explicite quand une sonde est indisponible.

Le gardien ne doit jamais confondre « aucun problème trouvé » avec « le diagnostic
n'a pas pu s'exécuter ». Les sondes pytest et Ruff signalent donc leurs propres
échecs comme des constats DIAGNOSTIC. Le cycle peut alors conserver les constats
précédents de la catégorie concernée au lieu de les déclarer résolus sans preuve.
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
CATEGORIE_DIAGNOSTIC = "DIAGNOSTIC"

GRAVITE_PAR_CATEGORIE = {
    CATEGORIE_BUG: "P2",
    CATEGORIE_QUALITE: "P5",
    CATEGORIE_CODE_MORT: "P6",
    CATEGORIE_DIAGNOSTIC: "P2",
}

DELAI_SECONDES = 300.0
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
            commande,
            cwd=str(RACINE),
            capture_output=True,
            text=True,
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
        brut = f"{self.categorie}|{self.fichier}|{self.description}"
        return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16]


_LIGNE_ECHEC = re.compile(r"^FAILED (?P<noeud>\S+)\s*$", re.MULTILINE)
_LIGNE_TRACE = re.compile(
    r"^(?P<fichier>\S+\.py):(?P<ligne>\d+): (?P<detail>.+)$", re.MULTILINE
)


def _diagnostic_indisponible(categorie: str, sortie: SortieCommande, raison: str) -> Constat:
    """Construit une preuve persistante qu'une catégorie n'a pas été vérifiée."""
    detail = (sortie.stderr or sortie.stdout or raison).strip()
    if len(detail) > 1000:
        detail = detail[:1000] + "…"
    return Constat(
        categorie=CATEGORIE_DIAGNOSTIC,
        gravite=GRAVITE_PAR_CATEGORIE[CATEGORIE_DIAGNOSTIC],
        description=f"diagnostic incomplet : {categorie}",
        fichier=categorie,
        preuve=f"{raison}; code={sortie.code}; {detail}",
    )


def diagnostiquer_bugs(executer: Executeur = executer_reel) -> List[Constat]:
    """Exécute pytest et refuse de conclure « propre » si pytest n'a pas abouti."""
    sortie = executer([sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"])

    traces_par_fichier = {}
    for trace in _LIGNE_TRACE.finditer(sortie.stdout):
        try:
            chemin_relatif = str(Path(trace.group("fichier")).resolve().relative_to(RACINE))
        except (ValueError, OSError):
            chemin_relatif = trace.group("fichier")
        traces_par_fichier.setdefault(
            chemin_relatif,
            f"{trace.group('fichier')}:{trace.group('ligne')}: {trace.group('detail')}",
        )

    constats = []
    for correspondance in _LIGNE_ECHEC.finditer(sortie.stdout):
        noeud = correspondance.group("noeud")
        fichier = noeud.split("::")[0]
        constats.append(
            Constat(
                categorie=CATEGORIE_BUG,
                gravite=GRAVITE_PAR_CATEGORIE[CATEGORIE_BUG],
                description=f"test en echec : {noeud}",
                fichier=fichier,
                preuve=traces_par_fichier.get(fichier, "(trace non capturee)"),
            )
        )

    # pytest: 0 = succès, 1 = tests échoués. Tout autre code signifie que la
    # sonde elle-même n'a pas produit un verdict fiable (collection, usage,
    # erreur interne, timeout...). Un code 1 sans FAILED parsable est aussi
    # incomplet : typiquement une erreur de collection.
    if sortie.code not in (0, 1) or (sortie.code == 1 and not constats):
        return [
            _diagnostic_indisponible(
                CATEGORIE_BUG, sortie, "pytest n'a pas produit de verdict exploitable"
            )
        ]
    return constats


def diagnostiquer_qualite(executer: Executeur = executer_reel) -> List[Constat]:
    """Exécute Ruff et distingue un dépôt propre d'une sonde Ruff en erreur."""
    sortie = executer(
        [sys.executable, "-m", "ruff", "check", ".", "--output-format=json"]
    )
    # Ruff utilise 0 pour propre, 1 pour violations, 2 pour erreur de l'outil.
    if sortie.code not in (0, 1):
        return [
            _diagnostic_indisponible(
                CATEGORIE_QUALITE, sortie, "ruff n'a pas produit de verdict exploitable"
            )
        ]
    try:
        violations = json.loads(sortie.stdout or "[]")
    except json.JSONDecodeError:
        logger.error("Sortie ruff illisible : %s", sortie.stdout[:200])
        return [
            _diagnostic_indisponible(
                CATEGORIE_QUALITE, sortie, "sortie JSON de ruff illisible"
            )
        ]
    if not isinstance(violations, list):
        return [
            _diagnostic_indisponible(
                CATEGORIE_QUALITE, sortie, "format JSON de ruff inattendu"
            )
        ]

    constats = []
    for v in violations:
        chemin = v.get("filename", "")
        try:
            chemin = str(Path(chemin).resolve().relative_to(RACINE))
        except (ValueError, OSError):
            pass
        code = v.get("code") or "?"
        constats.append(
            Constat(
                categorie=CATEGORIE_QUALITE,
                gravite=GRAVITE_PAR_CATEGORIE[CATEGORIE_QUALITE],
                description=f"{code} : {v.get('message', '')}".strip(),
                fichier=f"{chemin}:{(v.get('location') or {}).get('row', '?')}",
                preuve=json.dumps(v.get("location") or {}),
            )
        )
    return constats


def diagnostiquer_code_mort() -> List[Constat]:
    """Réutilise `scripts/orphelins.py` plutôt que dupliquer son analyse."""
    chemin_scripts = RACINE / "scripts"
    if str(chemin_scripts) not in sys.path:
        sys.path.insert(0, str(chemin_scripts))
    from orphelins import orphelins_reels

    return [
        Constat(
            categorie=CATEGORIE_CODE_MORT,
            gravite=GRAVITE_PAR_CATEGORIE[CATEGORIE_CODE_MORT],
            description=f"module non atteint par le chemin de reponse : {module}",
            fichier=module.replace(".", "/") + ".py",
        )
        for module in sorted(orphelins_reels())
    ]


def diagnostiquer_tout(executer: Executeur = executer_reel) -> List[Constat]:
    """Les diagnostics réels, du moins coûteux au plus coûteux."""
    return [
        *diagnostiquer_code_mort(),
        *diagnostiquer_qualite(executer),
        *diagnostiquer_bugs(executer),
    ]
