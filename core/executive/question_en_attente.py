"""Ce qu'ARENA a demandé et qui attend toujours une réponse.

**Le défaut que ce module ferme, mesuré le 20/09/2026.** Le propriétaire
demande un devis, ARENA demande le lieu du chantier, il répond « Medina » — et
reçoit trois paragraphes sur la ville sainte d'Arabie saoudite, sources
Wikipedia comprises.

La cause n'est pas la compréhension du modèle : on lui a posé une question de
culture générale, et il y a répondu correctement. `analyze_intent()` ne lit
**que le message courant**. « Medina » seul ne peut pas lui rappeler qu'un
devis attend son lieu de chantier.

**Et ce n'est pas un défaut du devis.** Le premier correctif ne regardait que
les trois questions du destinataire d'un devis — il aurait laissé le même
défaut partout ailleurs. Le propriétaire l'a dit :

    « si tu le règles seulement ici, sur d'autres sujets il peut répéter cette
    hallucination — tu dois régler le fond du problème »

Mesuré : au moins cinq chemins rendent un statut qui réclame une information
et repartent ensuite au classeur.

| Chemin | Ce qu'il réclame |
|---|---|
| `agents/plaquiste` | client, lieu, objet d'un devis ; étapes d'un planning |
| `agents/email` | destinataire, sujet d'un message |
| `agents/video_analyzer` | sujet, description d'une vidéo |
| `core/production/personnage_video` | ce qui manque à un personnage |

Ce module retient, **par session**, l'intention qui a posé la question. Le
tour suivant y retourne, sans modèle et sans un jeton dépensé.

**Trois règles :**

1. **Une question retenue n'est pas une prison.** Elle expire
   (`DELAI_DE_VALIDITE_SECONDES`), et un changement de sujet manifeste passe
   devant — c'est l'appelant qui en décide, ce module ne fait que se souvenir.
2. **Rien n'est deviné.** Seul un statut qui réclame explicitement une
   information est retenu. Un échec, un refus, un succès ne posent aucune
   question et n'attendent donc rien.
3. **La mémoire est bornée.** Un dictionnaire par session, plafonné, purgé de
   ses entrées périmées à chaque écriture : une session oubliée ne fait pas
   grossir le processus indéfiniment.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("usman.executive.question_en_attente")

#: Les statuts par lesquels un agent dit « il me manque quelque chose ».
#: Chacun est déjà rendu par au moins un chemin du dépôt — aucun n'est
#: inventé ici pour l'occasion.
STATUTS_EN_ATTENTE = frozenset({
    "INCOMPLET", "A_COMPLETER", "CLARIFICATION_REQUIRED",
})

#: Au-delà, la question n'attend plus. Une demi-heure : assez pour qu'il aille
#: chercher l'information, trop court pour qu'une phrase du lendemain matin
#: soit avalée par un devis de la veille.
DELAI_DE_VALIDITE_SECONDES = 30 * 60

#: Combien de sessions retenues au maximum. Au-delà, la plus ancienne part.
#: Sans ce plafond, un serveur qui tourne des mois garderait une entrée par
#: session jamais reprise.
SESSIONS_MAX = 500

#: Jusqu'où descendre dans le résultat d'un agent pour y trouver un statut.
#: Deux niveaux suffisent aux quatre chemins mesurés (`statut` à la racine
#: pour l'email, `document.statut` pour le devis) ; descendre indéfiniment
#: ferait dépendre le routage de la profondeur d'un dictionnaire.
PROFONDEUR_MAX = 2


@dataclass(frozen=True)
class QuestionEnAttente:
    """Une question posée par ARENA, et qui attend toujours sa réponse."""

    intention: str
    #: Ce qui manque, quand l'agent a su le nommer. Vide sinon — ce module
    #: ne le devine pas, et une liste vide reste une question en attente.
    champs: Tuple[str, ...]
    pose_le: float

    def perimee(self, maintenant: Optional[float] = None) -> bool:
        instant = time.time() if maintenant is None else maintenant
        return (instant - self.pose_le) > DELAI_DE_VALIDITE_SECONDES


#: `session_id` -> la question qu'ARENA y a laissée sans réponse.
_ATTENTES: Dict[str, QuestionEnAttente] = {}


def champs_reclames(resultat: Any, profondeur: int = 0) -> Optional[Tuple[str, ...]]:
    """Ce qu'un résultat d'agent réclame, ou `None` s'il ne réclame rien.

    Cherche un statut de `STATUTS_EN_ATTENTE` dans le résultat, à la racine
    ou un cran plus bas — les agents le posent aux deux endroits. Rend le
    tuple des champs manquants quand l'agent les a nommés, un tuple vide
    quand il réclame sans les nommer, et `None` quand il ne réclame rien.

    Le tuple vide et `None` disent deux choses différentes, et les confondre
    ferait soit oublier une question posée, soit en inventer une.
    """
    if not isinstance(resultat, dict) or profondeur > PROFONDEUR_MAX:
        return None

    statut = resultat.get("statut") or resultat.get("status")
    if isinstance(statut, str) and statut.upper() in STATUTS_EN_ATTENTE:
        manquants = resultat.get("manquants")
        if isinstance(manquants, (list, tuple)):
            return tuple(str(champ) for champ in manquants)
        return ()

    for valeur in resultat.values():
        trouve = champs_reclames(valeur, profondeur + 1)
        if trouve is not None:
            return trouve
    return None


def _purger(maintenant: float) -> None:
    """Retire les questions périmées, puis les plus anciennes si besoin."""
    for session, attente in list(_ATTENTES.items()):
        if attente.perimee(maintenant):
            del _ATTENTES[session]
    if len(_ATTENTES) > SESSIONS_MAX:
        trop = len(_ATTENTES) - SESSIONS_MAX
        for session, _ in sorted(_ATTENTES.items(), key=lambda p: p[1].pose_le)[:trop]:
            del _ATTENTES[session]


def noter(session_id: str, intention: str, resultat: Any,
          maintenant: Optional[float] = None) -> bool:
    """Retient la question posée par ce tour, ou oublie la précédente.

    Rend `True` quand ce tour a laissé une question en attente. Un tour qui
    n'en pose aucune **efface** ce qui attendait : la question a reçu sa
    réponse, ou l'agent est passé à autre chose. Sans cet effacement, une
    question à laquelle il a répondu continuerait d'aspirer ses phrases.
    """
    if not session_id or not intention:
        return False
    champs = champs_reclames(resultat)
    if champs is None:
        oublier(session_id)
        return False
    instant = time.time() if maintenant is None else maintenant
    _ATTENTES[session_id] = QuestionEnAttente(intention, champs, instant)
    _purger(instant)
    logger.info("Question en attente retenue pour %s : %s%s",
                session_id, intention,
                f" ({', '.join(champs)})" if champs else "")
    return True


def en_attente(session_id: str,
               maintenant: Optional[float] = None) -> Optional[QuestionEnAttente]:
    """La question laissée sans réponse dans cette session, si elle tient
    encore. Une question périmée est oubliée à la lecture."""
    attente = _ATTENTES.get(session_id or "")
    if attente is None:
        return None
    if attente.perimee(maintenant):
        oublier(session_id)
        logger.info("Question en attente perimee pour %s, oubliee.", session_id)
        return None
    return attente


def oublier(session_id: str) -> None:
    """Efface la question retenue pour cette session, s'il y en a une."""
    _ATTENTES.pop(session_id or "", None)


def tout_oublier() -> None:
    """Vide la mémoire. Pour les tests, et pour un redémarrage propre."""
    _ATTENTES.clear()
