"""Le message qu'un agent adresse a un autre, et la tache qu'il ouvre.

**Pourquoi un message plutot qu'une chaine (DEC-0145).** Jusqu'ici un agent
en appelait un autre avec une phrase et un dictionnaire libre. Rien ne disait
a quelle tache racine l'appel appartenait, a quelle profondeur, ni combien de
sous-taches la meme demande avait deja ouvertes : une collaboration recursive
ne pouvait etre ni bornee proprement, ni suivie.

Chaque appel porte desormais un `MessageAgent` : l'expediteur, le destinataire,
l'objectif, le contexte, les exigences, la forme attendue — et l'identite de
la tache (`task_id`, `parent_task_id`, `root_task_id`, `depth`). Les noms
d'agents n'y sont jamais codes en dur : ce sont les identifiants que les
agents declarent eux-memes au registre.

**Les garde-fous sont attaches a la RACINE**, pas a l'appel : la profondeur,
la chaine (pour detecter A -> B -> A) et le nombre total de sous-taches
voyagent dans le contexte asyncio (`TACHE_EN_COURS`). Un agent consulte qui
consulte a son tour n'a rien a transmettre a la main.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple


def _entier_env(nom: str, defaut: int) -> int:
    try:
        return max(1, int(os.getenv(nom, "") or defaut))
    except ValueError:
        return defaut


#: Profondeur maximale d'une chaine de collaboration (utilisateur -> A -> B ->
#: C...). Configurable ; au-dela, l'appel est refuse et l'agent continue seul.
PROFONDEUR_MAX = _entier_env("ARENA_COLLAB_PROFONDEUR_MAX", 4)

#: Sous-taches au plus pour UNE demande racine, toutes profondeurs et tous
#: paralleles confondus : ce qui empeche l'explosion en eventail.
TACHES_MAX_PAR_RACINE = _entier_env("ARENA_COLLAB_TACHES_MAX", 16)


def nouvel_identifiant() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class MessageAgent:
    """Une demande d'un agent a un autre. Aucun champ ne nomme un agent en dur."""

    sender: str
    recipient: str
    objective: str
    context: str = ""
    requirements: str = ""
    expected_output: str = ""
    priority: str = "normale"
    project_id: str = ""
    task_id: str = field(default_factory=nouvel_identifiant)
    parent_task_id: Optional[str] = None
    root_task_id: str = ""
    depth: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def texte_pour_le_destinataire(self) -> str:
        """Ce que le destinataire recoit comme `user_input` : l'objectif, puis
        ce qui l'encadre — seulement les parties renseignees."""
        parties = [self.objective.strip()]
        for titre, valeur in (("Contexte", self.context),
                              ("Exigences", self.requirements),
                              ("Resultat attendu", self.expected_output)):
            if valeur and str(valeur).strip():
                parties.append(f"{titre} : {str(valeur).strip()}")
        return "\n\n".join(p for p in parties if p)

    def en_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContexteTache:
    """La tache en cours pour CETTE execution — partagee par toutes ses
    sous-taches, parce que `compteur` est un meme objet mutable."""

    task_id: str
    root_task_id: str
    depth: int
    chaine: Tuple[str, ...]
    requete_racine: str
    project_id: str = ""
    compteur: Dict[str, int] = field(default_factory=lambda: {"taches": 0})


#: La tache en cours. `None` : on est a la racine (une demande de l'utilisateur).
TACHE_EN_COURS: ContextVar[Optional[ContexteTache]] = ContextVar(
    "tache_en_cours", default=None)


def refus(parent: Optional[ContexteTache], expediteur: str, destinataire: str
          ) -> Optional[str]:
    """La raison pour laquelle ce nouvel appel est refuse, ou `None`.

    Trois garde-fous, dans cet ordre : le cycle (le destinataire est deja dans
    la chaine, ou c'est l'expediteur), la profondeur, le budget de la racine.
    """
    chaine: List[str] = list(parent.chaine) if parent else []
    if destinataire == expediteur or destinataire in chaine:
        return f"boucle detectee : {' -> '.join(chaine + [expediteur, destinataire])}"
    profondeur = (parent.depth if parent else 0) + 1
    if profondeur > PROFONDEUR_MAX:
        return f"profondeur maximale atteinte ({PROFONDEUR_MAX})"
    if parent and parent.compteur["taches"] >= TACHES_MAX_PAR_RACINE:
        return f"budget de la demande atteint ({TACHES_MAX_PAR_RACINE} sous-taches)"
    return None


def ouvrir(parent: Optional[ContexteTache], expediteur: str, message: MessageAgent
           ) -> ContexteTache:
    """Rattache `message` a l'arbre de taches et rend le contexte de l'enfant."""
    compteur = parent.compteur if parent else {"taches": 0}
    compteur["taches"] += 1
    racine = parent.root_task_id if parent else message.task_id
    message.parent_task_id = parent.task_id if parent else None
    message.root_task_id = racine
    message.depth = (parent.depth if parent else 0) + 1
    message.project_id = message.project_id or (parent.project_id if parent else "") or racine
    return ContexteTache(
        task_id=message.task_id, root_task_id=racine, depth=message.depth,
        chaine=(parent.chaine if parent else ()) + (expediteur,),
        requete_racine=(parent.requete_racine if parent else message.objective),
        project_id=message.project_id, compteur=compteur)


@contextmanager
def tache_racine(objectif: str, project_id: str = "") -> Iterator[ContexteTache]:
    """Ouvre la tache racine d'UNE demande, si aucune n'est deja ouverte.

    Toutes les delegations faites dessous — en sequence, en parallele, a
    toute profondeur — partagent alors le meme `root_task_id`, le meme
    projet et le meme compteur : le budget vaut pour la demande entiere, pas
    pour chaque appel. Deja dans une tache : rien n'est ouvert, la tache en
    cours est rendue telle quelle.
    """
    en_cours = TACHE_EN_COURS.get()
    if en_cours is not None:
        yield en_cours
        return
    racine = nouvel_identifiant()
    tache = ContexteTache(task_id=racine, root_task_id=racine, depth=0, chaine=(),
                          requete_racine=objectif, project_id=project_id or racine)
    jeton = TACHE_EN_COURS.set(tache)
    try:
        yield tache
    finally:
        TACHE_EN_COURS.reset(jeton)
