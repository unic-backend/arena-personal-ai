"""Dire « oui » doit suffire — mais pas pour tout.

Defaut mesure le 02/09/2026, sur une capture d'ecran du proprietaire. Usman
prepare son devis PDF, l'annonce prêt, et affiche :

    Confirme avec l'identifiant aaffc054d9854d7abb94dc278bf90a44.

Le proprietaire repond « Fait le en pdf c'est bon ». Rien ne se passe. Il
reessaie. Rien. **Et rien ne pouvait se passer** : `POST
/api/actions/{id}/confirm` existe cote serveur et **aucun client ne l'appelle
jamais** — verifie par recherche sur tout `apps/pwa/src`. Un document prepare
sur son telephone ne pouvait donc etre confirme par aucun moyen, et attendait
indefiniment. C'est la raison pour laquelle il n'a jamais eu un seul PDF.

Ce module porte la moitie « phrase » de la reparation. L'autre moitie est un
bouton dans l'interface, qui reste le chemin principal.

**La regle, et elle n'est pas negociable : une phrase ne confirme que ce qui
reste sur la machine.**

Ecrire un fichier se defait — on le supprime. Envoyer un mail, publier sur ses
reseaux, supprimer chez un fournisseur : cela ne se rattrape pas, et un « oui »
mal place dans une conversation ne doit jamais suffire a le declencher. Ces
actions-la gardent le bouton, qui nomme ce qu'il valide.

Le partage entre les deux ne se decide **pas** ici : il lit
`INTERRUPTEURS_OBLIGATOIRES` (`core/permissions/controle.py`), le plancher que
le depot tient deja pour les trois effets irreversibles — publier, envoyer,
supprimer. Ecrire une seconde liste ici, c'est se donner un endroit pour se
contredire ; celle-la vit dans le code precisement parce qu'aucune
configuration ne doit pouvoir l'entamer.

Choix du proprietaire, 02/09/2026 : « les deux — le bouton, et la phrase pour
les documents seulement, jamais pour un envoi de mail ou une publication ».
"""
from __future__ import annotations

import logging
import re
from typing import Any, List, Optional, Tuple

from core.actions.attente import ActionEnAttente
from core.permissions.controle import INTERRUPTEURS_OBLIGATOIRES

logger = logging.getLogger("usman.actions.confirmation")

#: Ce qui vaut « oui ». Volontairement court et ferme : la phrase doit etre une
#: confirmation ET RIEN D'AUTRE. « oui mais change le prix » n'en est pas une —
#: elle porte une demande, et la traiter comme un accord ferait partir un
#: document que le proprietaire voulait justement corriger.
#:
#: « fais le en pdf c'est bon » (sa phrase reelle) passe : les mots qui
#: entourent le « c'est bon » ne demandent rien de plus que ce qui est deja
#: prepare.
CONFIRMATION = re.compile(
    r"^\W*(?:"
    r"oui|ouais|ok|okay|d'accord|daccord|c'?est\s+bon|c'?est\s+ok"
    r"|vas[- ]?y|go|confirme?|je\s+confirme|valide?|je\s+valide"
    r"|envoie|fais[- ]?le|fait[- ]?le|parfait|nickel|impeccable"
    r"|fais[- ]?le\s+en\s+pdf|fait[- ]?le\s+en\s+pdf"
    r")\W*$",
    re.IGNORECASE)

#: La meme chose, mais tolerante a quelques mots autour — « fais le en pdf
#: c'est bon », « ok vas-y ». Le texte ne doit contenir AUCUN mot qui demande
#: autre chose : c'est ce que verifie `RESERVE`.
CONFIRMATION_DANS_LA_PHRASE = re.compile(
    r"\b(?:oui|ok|okay|d'?accord|c'?est\s+bon|vas[- ]?y|confirme|je\s+confirme"
    r"|valide|je\s+valide|parfait|nickel|impeccable|fai[st][- ]?le)\b",
    re.IGNORECASE)

#: Ce qui annule la lecture « c'est un simple oui ». Une phrase qui corrige,
#: doute ou demande autre chose n'est pas un accord, meme si elle contient
#: « ok ». Mieux vaut ne pas confirmer et qu'il reformule, que confirmer un
#: document qu'il voulait changer.
RESERVE = re.compile(
    r"\b(?:mais|sauf|par\s+contre|change|changer|corrige|corriger|modifie|modifier"
    r"|ajoute|ajouter|enleve|enlever|retire|retirer|remplace|remplacer|attends?"
    r"|pas\s+encore|annule|annuler|non|plutot|plut[oô]t|avant\s+de|d'?abord"
    r"|pourquoi|comment|combien|est[- ]ce\s+que)\b",
    re.IGNORECASE)


def est_une_confirmation(texte: str) -> bool:
    """La phrase dit-elle « oui » — et seulement « oui » ?

    Une phrase qui porte la moindre reserve, correction ou question rend
    `False`. Le cout des deux erreurs n'est pas le meme : ne pas reconnaitre
    un accord fait retaper trois lettres ; en reconnaitre un a tort produit un
    document que le proprietaire allait corriger.
    """
    texte = (texte or "").strip()
    if not texte:
        return False
    if RESERVE.search(texte):
        return False
    if CONFIRMATION.match(texte):
        return True
    # Tolerance aux quelques mots autour, mais pas a une phrase entiere : plus
    # elle est longue, moins « ok » en est le sujet.
    return bool(len(texte.split()) <= 6 and CONFIRMATION_DANS_LA_PHRASE.search(texte))


def _service_et_action(action: ActionEnAttente, registre: Any) -> Optional[Tuple[str, str]]:
    """Le couple (service, action) de la politique, ou None s'il est illisible.

    Il n'est pas stocke dans la ligne en attente — elle porte le nom du
    connecteur et celui de la capacite. On le relit donc sur le connecteur
    lui-meme, seule source qui le sait vraiment.
    """
    if registre is None:
        return None
    try:
        connecteur = registre.obtenir(action.connecteur)
        if connecteur is None:
            return None
        capacite = connecteur.capacites().get(action.capacite)
        if capacite is None:
            return None
        return (connecteur.service, capacite.action)
    except Exception as erreur:  # noqa: BLE001 — un connecteur casse n'autorise rien
        logger.warning("Classement impossible pour %s.%s : %s",
                       action.connecteur, action.capacite, erreur)
        return None


def confirmable_par_phrase(action: ActionEnAttente, registre: Any) -> bool:
    """Un « oui » suffit-il pour CETTE action ?

    Non des que l'effet quitte la machine ou detruit quelque chose : ces
    actions-la sont celles de `INTERRUPTEURS_OBLIGATOIRES`, et elles gardent
    le bouton.

    **Un doute repond non.** Une action dont on ne parvient pas a lire le
    couple (service, action) — connecteur absent, capacite disparue — n'est
    pas confirmee par une phrase : on ne sait pas ce qu'on autoriserait.
    """
    couple = _service_et_action(action, registre)
    if couple is None:
        return False
    return couple not in INTERRUPTEURS_OBLIGATOIRES


def a_confirmer_par_phrase(
    en_attente: List[ActionEnAttente], registre: Any
) -> Optional[ActionEnAttente]:
    """L'unique action qu'un « oui » peut confirmer maintenant, ou None.

    `None` quand il n'y en a aucune, quand la seule qui attend exige le bouton,
    **et aussi quand plusieurs attendent** : « oui » ne dit pas laquelle, et
    choisir a sa place est exactement ce qu'une confirmation existe pour
    empecher.
    """
    confirmables = [a for a in en_attente if confirmable_par_phrase(a, registre)]
    if len(confirmables) != 1:
        return None
    # Une autre action attend le bouton : la phrase ne doit pas donner
    # l'impression d'avoir tout valide.
    if len(en_attente) != 1:
        return None
    return confirmables[0]
