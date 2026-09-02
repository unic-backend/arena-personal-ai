"""Usman se relit avant de repondre — sans faire attendre le proprietaire.

Sa troisieme plainte, le 02/09/2026 : « il se trompe et ne le voit pas ». Et
sa contrainte, dans la meme phrase : « mais trop il doit etre rapide dans les
reflexions ».

Les deux ensemble excluent la solution evidente. Faire relire la reponse par
un second appel au modele doublerait l'attente — sur sa machine, ou une
reponse prend deja plusieurs secondes, ce serait le rendre deux fois plus lent
pour attraper ce qu'un test peut prouver instantanement.

**Donc : que des controles deterministes.** Aucun appel de modele, aucune
seconde d'attente. Ce qui est verifiable par comparaison est verifie ; le
reste ne l'est pas, et ce module ne pretend pas le contraire.

**Il ne corrige rien.** Il signale, sous la reponse, avec la ligne fautive et
ce qui etait attendu. Corriger d'autorite un montant dans un document
commercial serait pire que le signaler : le proprietaire tranche, c'est son
tarif et son client. C'est deja la regle de `controle_prix.py`, dont ce
module etend la portee.

**Ce qu'il attrape aujourd'hui : un prix altere.** Un seul controle, et c'est
assume — c'est celui qui coute de l'argent quand il passe. `controle_prix`
existait depuis le 27/08/2026 et ne tournait QUE dans l'agent devis
(`plaquiste_agent.py:1388`). Mesure du 02/09/2026 : la conversation generale,
qui cite ses tarifs tout aussi bien, n'etait verifiee par rien du tout.

Ajouter un controle ici demande la meme chose qu'ailleurs dans ce depot : que
la faute soit **prouvable**. Un controle qui crie a tort est un controle qu'on
eteint.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from agents.plaquiste.controle_prix import Anomalie, avertissement, verifier_prix

logger = logging.getLogger("usman.relecture")


@dataclass
class Relecture:
    """Ce que la relecture a trouve dans une reponse deja ecrite.

    Attributes:
        anomalies: les prix qui ne correspondent pas a la grille.
        note: le texte a joindre sous la reponse, vide s'il n'y a rien a dire.
    """

    anomalies: List[Anomalie] = field(default_factory=list)
    note: str = ""

    @property
    def a_trouve_quelque_chose(self) -> bool:
        return bool(self.anomalies)


def relire(reponse: str, metier: Dict[str, Any]) -> Relecture:
    """Relit une reponse deja redigee. **Ne la modifie jamais.**

    Instantane par construction : aucune des verifications ici n'appelle un
    modele ni ne sort de la machine.

    Args:
        reponse: le texte qu'Usman s'apprete a rendre.
        metier: les connaissances metier, seule source des prix justes.

    Returns:
        Ce qui a ete trouve, et la note a joindre. Rien trouve = note vide,
        et la reponse part telle quelle.
    """
    if not reponse or not metier:
        return Relecture()

    try:
        anomalies = verifier_prix(reponse, metier)
    except Exception as erreur:  # noqa: BLE001 — une relecture qui casse ne
        # doit pas emporter la reponse : le proprietaire prefere une reponse
        # non relue a pas de reponse du tout.
        logger.warning("Relecture impossible : %s", erreur)
        return Relecture()

    if not anomalies:
        return Relecture()

    logger.info("Relecture : %d prix a verifier avant envoi.", len(anomalies))
    return Relecture(anomalies=anomalies, note=avertissement(anomalies))


def avec_la_relecture(reponse: str, metier: Dict[str, Any]) -> str:
    """La reponse, suivie de ce que la relecture a trouve.

    La reponse est rendue **entiere et inchangee** meme quand la relecture
    trouve quelque chose : ce qu'il a demande reste ce qu'il recoit, avec
    l'avertissement en dessous. Une reponse retenue parce qu'un controle a
    doute est une reponse perdue.
    """
    relecture = relire(reponse, metier)
    return f"{reponse}{relecture.note}" if relecture.a_trouve_quelque_chose else reponse
