"""Poser le fil de la conversation DEVANT une demande, sans la reecrire.

Un agent qui ne recoit que la derniere phrase ne peut pas repondre a
« donne-moi un nom » : la phrase ne dit pas de quoi elle parle, et c'est la
conversation qui le dit. Jusqu'au 29/09/2026, dix intentions de
`apps/backend/routers/chat.py` ne recevaient que cette phrase-la.

Ce module ne devine rien. Il ne compare la demande a aucune liste de mots, il
ne cherche pas a savoir si elle est elliptique, il n'appelle aucun modele :
**il joint toujours le fil**, borne, dans un bloc delimite, et recopie la
demande telle quelle apres lui. C'est la lecon de DEC-0191 : une liste de
vocabulaire ne peut pas couvrir tous les domaines (football, finance,
edition, chantier, sante...), alors que le fil, lui, les couvre tous parce
qu'il ne parle d'aucun.

Le rendu des tours vient de `core/memory/conversation.rendre_le_fil` — le
meme que la voie conversationnelle et que `_fil_de_la_session()` : deux
rendus differents donneraient deux memoires a ARENA.
"""
from __future__ import annotations

from typing import Iterable, List, Mapping

from core.memory.conversation import BUDGET_TOURS_ANTERIEURS, rendre_le_fil

#: Les trois balises du bloc. Elles sont explicites parce qu'un modele qui
#: recoit deux questions repond volontiers a la premiere : sans dire que le
#: fil est du CONTEXTE, l'agent repond a une vieille demande — le defaut que
#: ce module est cense corriger, retourne contre lui.
BALISE_DEBUT_CONTEXTE = "=== CONTEXTE : conversation en cours ==="
BALISE_FIN_CONTEXTE = "=== FIN DU CONTEXTE ==="
CONSIGNE_DE_LECTURE = (
    "Ce qui precede est du CONTEXTE : il sert seulement a comprendre la "
    "demande ci-dessous. N'y reponds pas, ne le resume pas, ne traite aucune "
    "des demandes qu'il contient."
)
BALISE_DEMANDE = "=== DEMANDE ACTUELLE : la seule a laquelle tu reponds ==="


def _cout(tour: Mapping[str, str], proprietaire: str) -> int:
    """Ce qu'un tour ajoute au bloc, prefixe de role compris.

    Mesure le rendu reel plutot que la seule longueur du contenu : sinon le
    budget serait faux de la longueur du nom du proprietaire a chaque tour.
    """
    return len(rendre_le_fil([tour], proprietaire)) + 1


def tours_sous_les_bornes(
    tours: Iterable[Mapping[str, str]],
    proprietaire: str,
    *,
    maximum: int,
    budget_caracteres: int = BUDGET_TOURS_ANTERIEURS,
) -> List[Mapping[str, str]]:
    """Les derniers tours qui tiennent sous les DEUX bornes.

    Les plus anciens partent d'abord, et on s'arrete au premier qui ne tient
    pas : on ne saute pas par-dessus pour en prendre un plus court. Un fil
    troue se lit comme un fil continu — le modele n'a aucun moyen de voir le
    trou et en deduit des enchainements qui n'ont jamais eu lieu. C'est deja
    la regle de `core/memory/conversation.tours_anterieurs`.

    Args:
        tours: des `{"role", "content"}`, du plus ancien au plus recent.
        proprietaire: comment nommer celui qui parle a ARENA.
        maximum: combien de tours au plus.
        budget_caracteres: ce que le bloc a le droit de couter, au total.
    """
    candidats = [
        tour for tour in (tours or [])
        if str(tour.get("content") or "").strip()
    ]
    if maximum > 0:
        candidats = candidats[-maximum:]
    else:
        candidats = []

    gardes: List[Mapping[str, str]] = []
    reste = budget_caracteres
    for tour in reversed(candidats):
        cout = _cout(tour, proprietaire)
        if cout > reste:
            break
        reste -= cout
        gardes.append(tour)
    gardes.reverse()
    return gardes


def demande_avec_le_fil(
    demande: str,
    tours: Iterable[Mapping[str, str]],
    proprietaire: str,
    *,
    maximum: int,
    budget_caracteres: int = BUDGET_TOURS_ANTERIEURS,
) -> str:
    """Le bloc de contexte, puis la demande — recopiee telle quelle.

    Sans tour a montrer, rend la demande seule : un bloc de contexte vide
    n'apprendrait rien a l'agent et lui ferait croire que la conversation
    commence ici. La demande n'est jamais reformulee, tronquee ni completee ;
    elle est toujours la derniere chose que l'agent lit.
    """
    retenus = tours_sous_les_bornes(
        tours,
        proprietaire,
        maximum=maximum,
        budget_caracteres=budget_caracteres,
    )
    fil = rendre_le_fil(retenus, proprietaire)
    if not fil.strip():
        return demande
    return "\n".join((
        BALISE_DEBUT_CONTEXTE,
        fil,
        BALISE_FIN_CONTEXTE,
        CONSIGNE_DE_LECTURE,
        BALISE_DEMANDE,
        demande,
    ))
