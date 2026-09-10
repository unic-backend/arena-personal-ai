"""Choisir les compétences pertinentes — projet ET tâche, jamais l'un sans
l'autre (mission §5).

**Réutilise `core/specialistes/selection.py`, ne le duplique pas** :
`_sans_accents`/`_reconnait` y font déjà exactement ce qu'il faut — un mot
reconnu comme un MOT, accents ignorés. Réécrire cette paire ici ferait
diverger deux définitions de « ce mot apparaît-il vraiment » pour la même
raison que ce module existe : ne jamais dupliquer.

**Deux filtres, dans l'ordre, jamais un seul** :

1. **Le projet.** Une compétence dont aucune technologie déclarée n'est
   détectée dans le dépôt n'entre jamais en lice — un projet React ne voit
   jamais la compétence Playwright s'il n'a pas Playwright (mission §5,
   contre-exemple exact : ne pas montrer SEO/Tailwind/Three.js pour
   corriger un test Playwright dans un dépôt qui a aussi ces
   technologies).
2. **La tâche.** Parmi les compétences dont la technologie EST présente,
   seules celles que la demande appelle par ses mots gagnent des points —
   même moteur de poids que `core/specialistes/selection.py`
   (`_poids`/`_reconnait`), donc le même comportement déjà vérifié : un
   mot long compte plus qu'un mot court, la position ne joue aucun rôle,
   aucun appel de modèle.

**Zéro est une réponse ici aussi.** Une tâche qui ne nomme aucune
technologie de celles détectées ne charge rien — mieux vaut zéro
compétence chargée qu'une compétence non pertinente qui gonfle le prompt.
"""
from __future__ import annotations

from typing import List, Sequence

from core.skills.registry import Competence
from core.specialistes.selection import _reconnait, _sans_accents

#: Le plafond — même raisonnement que `core/specialistes/selection.py` :
#: au-delà, ce n'est plus une sélection, c'est un sommaire. Légèrement plus
#: haut (3 au lieu de 2) parce qu'une compétence technique est plus
#: étroite qu'une méthode de métier — trois technologies coexistent
#: couramment (« composant React avec des tests Playwright », mission §9).
MAXIMUM = 3


def _poids_tache(competence: Competence, texte_normalise: str) -> int:
    total = 0
    for mot in competence.mots_taches:
        normalise = _sans_accents(mot)
        if normalise and _reconnait(normalise, texte_normalise):
            total += len(normalise)
    return total


def choisir_competences(
    competences: Sequence[Competence],
    technologies_detectees: Sequence[str],
    demande: str,
    maximum: int = MAXIMUM,
) -> List[Competence]:
    """Les compétences que CE projet et CETTE demande appellent vraiment.

    Args:
        competences: le registre chargé (`charger_registre()`), déjà
            filtré par l'appelant sur les états de confiance acceptables
            s'il le souhaite — ce module ne juge jamais la confiance,
            seulement la pertinence.
        technologies_detectees: sortie de `detecter_technologies()`.
        demande: la tâche telle que formulée.
        maximum: le plafond.

    Returns:
        De zéro à `maximum` compétences, de la plus appelée à la moins
        appelée. Une compétence sans technologie présente dans le projet
        n'apparaît JAMAIS, quel que soit son score de mots.
    """
    ensemble_tech = set(technologies_detectees)
    candidates = [c for c in competences
                  if any(t in ensemble_tech for t in c.technologies)]
    if not candidates:
        return []

    texte = _sans_accents(demande)
    if not texte.strip():
        # Aucune tâche à lire : la seule chose déterministe à faire est de
        # ne rien choisir plutôt que deviner laquelle des candidates compte.
        return []

    notees = [(c, _poids_tache(c, texte)) for c in candidates]
    retenues = [(c, p) for c, p in notees if p > 0]
    retenues.sort(key=lambda couple: (-couple[1], couple[0].identifiant))
    return [c for c, _ in retenues[:maximum]]
