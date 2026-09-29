"""Rattachement déterministe d'une question elliptique au sujet du fil.

Aucun modèle ne complète ni ne reformule la demande : seuls des mots déjà
écrits par le propriétaire peuvent être ajoutés, dans un bloc séparé.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

# Reprises de agents/fresh_info/fresh_info_agent.py. Elles vivent ici aussi
# pour que l'ancrage transversal ne dépende pas d'un agent particulier.
MOTS_VIDES_ANCRAGE = frozenset({
    "a", "ai", "au", "aux", "avec", "avait", "ce", "ces", "cet", "cette",
    "comme", "dans", "de", "des", "du", "elle", "elles", "en", "entre", "est",
    "et", "ete", "été", "etait", "était", "eux", "fait", "faire", "il", "ils",
    "la", "le", "les", "leur", "leurs", "lui", "ma", "maintenant", "mes", "mon",
    "ne", "notre", "nous", "ou", "où", "par", "pas", "pour", "que", "quel",
    "quelle", "quelles", "quels", "qui", "sa", "sans", "sera", "serait", "ses",
    "son", "sont", "sur", "ta", "tes", "ton", "tu", "un", "une", "vos", "votre",
    "vous", "web", "internet", "verifie", "vérifie", "rapidement", "parle", "dis",
    "donne", "question", "source", "sources", "fc", "exact", "exacte", "recent",
    "récente", "récent", "aujourd'hui", "aujourd’hui", "pourquoi", "comment",
    "quand", "combien", "lequel", "laquelle", "lesquels", "lesquelles",
    # Une liaison ne devient jamais artificiellement le sujet du fil.
    "alors", "donc", "mais", "puis", "ensuite",
})
TERMES_SUIVI_GENERIQUES = frozenset({
    "buteur", "buteurs", "score", "scores", "resultat", "résultat", "resultats",
    "résultats", "gagnant", "gagnants", "gagne", "gagné", "gagner", "vainqueur",
    "vainqueurs", "homme", "match", "joueur", "joueurs", "statistique",
    "statistiques", "stats", "classement", "composition", "compo", "details",
    "détails", "autre", "autres", "deuxieme", "deuxième", "premier", "première",
    "apres", "après", "nom",
})
DEICTIQUES_SUIVI = frozenset({
    "cela", "ça", "celui", "celle", "ceux", "celles", "cette", "ces", "lui",
    "elle", "eux", "elles",
})
PRONOM_ACCOLE = re.compile(
    r"-(?:t-)?(?:il|elle|ils|elles|on|moi|toi|nous|vous|je|tu|ce|y|en|le|la|les|lui|leur)$"
)

_MOTS = re.compile(r"[\wÀ-ÿ-]+")


def _termes(texte: str) -> list[str]:
    """Mots susceptibles de nommer un sujet, dans leur graphie d'origine."""
    resultat: list[str] = []
    for brut in _MOTS.findall(texte or ""):
        mot = brut.casefold().strip("'’_-")
        # « donne-moi » est un verbe et son pronom, et non une entité. On
        # retire d'abord le pronom afin d'évaluer « donne » normalement.
        mot = PRONOM_ACCOLE.sub("", mot)
        if (not mot or mot.isdigit() or mot in MOTS_VIDES_ANCRAGE
                or mot in TERMES_SUIVI_GENERIQUES or mot in DEICTIQUES_SUIVI):
            continue
        if len(mot) < 3 and not (len(brut) >= 2 and brut.isupper()):
            continue
        resultat.append(mot)
    return resultat


def ancrer_question(question: str, historique: Sequence[Mapping[str, str]]) -> str:
    """Ajoute le dernier sujet utilisateur si ``question`` est elliptique.

    Une question qui possède déjà un terme spécifique est rendue octet pour
    octet. Le sujet est toujours un bloc voisin, jamais une reformulation.
    """
    if _termes(question):
        return question
    for tour in reversed(historique):
        if tour.get("role") not in {"user", "utilisateur"}:
            continue
        sujet = _termes(tour.get("content", ""))
        if sujet:
            return f"{question}\n\nSujet du tour précédent : {' '.join(sujet)}"
    return question
