"""L'instantané de projet : ce qu'un agent de codage doit savoir AVANT de
relire le dépôt à l'aveugle — jamais un remplacement de la lecture, juste
son économie.

Mission ARENA × OPENCONTEXT (10/09/2026). Étudier `0xranx/OpenContext`
(commit `0649e71`, MIT) et améliorer l'architecture mémoire/contexte-projet
existante d'ARENA, sans doublon. Rapport complet →
`docs/audits/opencontext_audit.md`.

**Le manque mesuré, avant d'écrire une ligne** : `PROJECT_MEMORY/` existe
depuis des semaines et `CLAUDE.md` dit à un humain de le lire en premier —
mais `agents/dioumtoukay/dioumtoukay_agent.py::_reperes()`, le SEUL endroit
qui prépare le point de départ d'une tâche de codage, ne le lisait jamais.
Chaque tâche partait donc à l'aveugle, exactement comme avant que
`_reperes()` lui-même soit écrit pour la racine du dépôt (son propre
commentaire le dit : « deux tours perdus au départ comptent »).
`PROJECT_MEMORY/ACTIVE_WORK.md` porte depuis des semaines l'aveu « périmé
au-delà de PR #34 » : personne ne le mesure, tout le monde le lit quand même
— exactement le défaut que ce module mesure au lieu de répéter.

**Ce que ce module N'EST PAS** : ni un second système de mémoire (`core/
memory/`), ni un second RAG (`tools/rag/`, `core/connectors/claude_context.py`,
`txtai_search.py`), ni un second graphe de code (`core/connectors/
graphify.py`). Il ne LIT que des fichiers Markdown déjà écrits par
quelqu'un — jamais de vecteur, jamais d'index, jamais d'appel modèle,
jamais d'écriture. Ce que `core/context/recherche_unifiee.py` compose déjà
(code/mémoire/internet) reste inchangé ; ceci en devient une QUATRIÈME
source, et aussi ce que Dioumtoukay lit directement avant sa première
action, exactement comme il lit déjà la branche git et la racine du dépôt.

**La fraîcheur, mesurée, jamais assez fine pour mentir par excès de
précision.** Chaque fichier suivi porte déjà sa propre date déclarée
(« Mise à jour : AAAA-MM-JJ », convention déjà en place dans ce dépôt). Ce
module compare cette date au nombre RÉEL de commits touchés depuis
(`git log --since`), sur le dépôt ENTIER — jamais un mappage fichier→dossiers
deviné, qui serait précis en apparence et faux en pratique dès qu'une
convention change. Un compte de commits n'est pas une preuve de PERTINENCE
(un commit sur une zone sans rapport ne rend pas `PROJECT_MAP.md` faux),
mais s'il vaut zéro, c'est une vraie garantie : rien n'a changé depuis,
la lecture peut être évitée. S'il est positif, c'est un signal à lire,
jamais un verdict — la source fait toujours autorité (mission §12).

**Racine, jamais figée sur ARENA lui-même.** `contexte_unifie.py` le dit
déjà : « le dépôt d'ARENA lui-même par défaut, un autre projet sur demande ».
Ce module prend une racine en paramètre ; un projet sans `PROJECT_MEMORY/`
ni `CLAUDE.md` rend un instantané vide, jamais un instantané inventé —
l'absence se lit comme une absence, même discipline que `_reperes()`.

**Rien de persisté, rien à sécuriser en plus.** Ce module ne stocke aucun
état propre : chaque appel relit les fichiers réels au moment de l'appel.
Aucune fenêtre où un instantané pourrait mentir plus longtemps que les
fichiers eux-mêmes.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("usman.context.instantane_projet")

#: Fichiers toujours inclus quand ils existent, dans cet ordre — le plus
#: court et le plus critique (zones verrouillées) ne doit jamais être coupé
#: par le budget avant d'avoir été vu.
FICHIERS_SUIVIS: tuple[tuple[str, str], ...] = (
    ("PROJECT_MEMORY/LOCKED_ZONES.md", "Zones verrouillées"),
    ("PROJECT_MEMORY/PROJECT_MAP.md", "Carte du projet"),
)

#: Nombre de décisions récentes dont on garde le TITRE seul (jamais le
#: corps : `docs/DECISIONS.md` peut peser plusieurs centaines de Ko).
DECISIONS_RECENTES_MAX = 8

#: Budget total, en caractères — approximatif mais réel : ~4 caractères par
#: jeton pour du français mêlé de code est une estimation prudente, jamais
#: présentée comme une mesure de jetons exacte (aucun tokenizer n'est
#: appelé ici). Ce texte est relu à CHAQUE tour de Dioumtoukay (`_invite`
#: le réinjecte), donc son coût se multiplie par le nombre de tours —
#: contrairement à une donnée lue une fois et gardée en mémoire de travail.
BUDGET_CARACTERES_MAX = 8000

_DATE_DECLAREE = re.compile(r"Mise\s*à\s*jour\s*:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_TITRE_DECISION = re.compile(r"^##\s+(DEC-\d+\s+—.+)$", re.MULTILINE)

DELAI_GIT_SECONDES = 10.0


@dataclass
class FraicheurFichier:
    """Ce que dit le fichier lui-même, et ce que dit le dépôt — jamais fondus."""

    chemin: str
    date_declaree: Optional[str]
    commits_depuis: Optional[int]  #: None si la date est absente ou git indisponible.

    @property
    def perime(self) -> bool:
        return bool(self.commits_depuis)

    def bandeau(self) -> str:
        if self.date_declaree is None:
            return f"{self.chemin} : aucune date déclarée."
        if self.commits_depuis is None:
            return f"{self.chemin} : déclaré à jour le {self.date_declaree} (dépôt git indisponible pour vérifier)."
        if self.commits_depuis == 0:
            return f"{self.chemin} : à jour (déclaré {self.date_declaree}, aucun commit depuis)."
        pluriel = "s" if self.commits_depuis > 1 else ""
        return (f"{self.chemin} : déclaré {self.date_declaree}, mais {self.commits_depuis} "
                f"commit{pluriel} sont passés depuis sur le dépôt — peut-être périmé.")


@dataclass
class InstantaneProjet:
    """Ce qu'on rend : le texte prêt à injecter, plus ce qu'il faudrait
    vérifier avant de le croire aveuglément."""

    texte: str
    fraicheurs: List[FraicheurFichier] = field(default_factory=list)
    tronque: bool = False

    @property
    def vide(self) -> bool:
        return not self.texte


def _executer_git(racine: Path, arguments: List[str]) -> Optional[str]:
    """`None` si git est absent, le dossier n'est pas un dépôt, ou la
    commande échoue — jamais une chaîne vide confondue avec « zéro »."""
    try:
        resultat = subprocess.run(
            ["git", *arguments], cwd=racine, capture_output=True, text=True,
            timeout=DELAI_GIT_SECONDES, check=False)
    except (OSError, subprocess.TimeoutExpired) as erreur:
        logger.debug("git indisponible pour l'instantané de projet : %s", erreur)
        return None
    if resultat.returncode != 0:
        return None
    return resultat.stdout


def _date_declaree(contenu: str) -> Optional[str]:
    trouve = _DATE_DECLAREE.search(contenu)
    return trouve.group(1) if trouve else None


def _fraicheur(racine: Path, chemin_relatif: str, contenu: str) -> FraicheurFichier:
    date = _date_declaree(contenu)
    commits: Optional[int] = None
    if date is not None:
        sortie = _executer_git(racine, ["log", f"--since={date}", "--oneline"])
        if sortie is not None:
            commits = len([ligne for ligne in sortie.splitlines() if ligne.strip()])
    return FraicheurFichier(chemin=chemin_relatif, date_declaree=date, commits_depuis=commits)


def _decisions_recentes(racine: Path) -> Optional[str]:
    """Les titres des dernières décisions — jamais leur corps. `None` si le
    fichier n'existe pas ici (un projet sans `docs/DECISIONS.md` n'en a
    simplement pas)."""
    chemin = racine / "docs" / "DECISIONS.md"
    try:
        contenu = chemin.read_text(encoding="utf-8")
    except OSError:
        return None
    titres = _TITRE_DECISION.findall(contenu)
    if not titres:
        return None
    recents = titres[-DECISIONS_RECENTES_MAX:]
    recents.reverse()  # la plus récente d'abord
    return "Décisions récentes (titres seuls — lire docs/DECISIONS.md pour le corps) :\n" + \
        "\n".join(f"- {t}" for t in recents)


def instantane(racine: Path) -> InstantaneProjet:
    """L'instantané de `racine`, ou un instantané vide si rien n'y ressemble
    à un projet suivi — jamais un contenu deviné pour un dossier sans
    mémoire opérationnelle."""
    racine = Path(racine)
    blocs: List[str] = []
    fraicheurs: List[FraicheurFichier] = []

    for chemin_relatif, libelle in FICHIERS_SUIVIS:
        chemin = racine / chemin_relatif
        try:
            contenu = chemin.read_text(encoding="utf-8")
        except OSError:
            continue
        fraicheurs.append(_fraicheur(racine, chemin_relatif, contenu))
        blocs.append(f"### {libelle} ({chemin_relatif})\n{contenu.strip()}")

    decisions = _decisions_recentes(racine)
    if decisions:
        blocs.append(decisions)

    if not blocs:
        return InstantaneProjet(texte="", fraicheurs=[])

    bandeau_fraicheur = "\n".join(f.bandeau() for f in fraicheurs) if fraicheurs else ""
    entete = "## Instantané du projet (lu, pas relu — vérifier avant d'agir dessus)\n"
    corps = entete + (bandeau_fraicheur + "\n\n" if bandeau_fraicheur else "") + "\n\n".join(blocs)

    tronque = False
    if len(corps) > BUDGET_CARACTERES_MAX:
        corps = corps[:BUDGET_CARACTERES_MAX] + \
            "\n\n[... instantané tronqué au budget — lire les fichiers cités pour le reste ...]"
        tronque = True

    return InstantaneProjet(texte=corps, fraicheurs=fraicheurs, tronque=tronque)
