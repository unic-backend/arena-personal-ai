"""Le fil d'une demande : un identifiant, du premier octet HTTP a la derniere action.

Le defaut que ce module ferme, mesure le 13/09/2026 : `request_id` n'existait
**nulle part** dans le depot — zero occurrence dans `core/`, `apps/`, `agents/`.
`/api/actions` montrait ce qu'ARENA avait tente, `/api/observability` ce que les
voies avaient coute, et **rien ne reliait les deux a une meme demande**. Quand le
proprietaire dit « ce truc de ce matin n'a pas marche », il n'y avait aucun moyen
de retrouver, parmi trente actions, les quatre qui venaient de sa phrase.

## Pourquoi un `contextvars` et pas un parametre de plus

Faire descendre un `request_id` a travers les signatures existantes
demanderait de toucher les routeurs, les agents, les connecteurs et le journal
— la reecriture que la mission interdit, pour une information qui ne change
aucun comportement.

Une variable de module ne conviendrait pas non plus, et pas par elegance : le
serveur est `async` et sert plusieurs demandes en meme temps. Une globale serait
ecrasee par la demande suivante, et le journal attribuerait les actions de l'un
au fil de l'autre — une trace fausse, ce qui est pire qu'aucune trace.

`contextvars` est fait exactement pour cela : la valeur suit le `await`, et
chaque tache en garde sa propre copie.

## Deux regles

1. **`fil_courant()` rend `None` quand aucun fil n'est pose.** Jamais un
   identifiant fabrique pour remplir la colonne : un appel en ligne de commande,
   une tache de fond ou un test n'ont pas de demande HTTP derriere eux, et le
   dire est une information. Un `None` se lit « hors demande » ; un faux
   identifiant se lirait « demande introuvable ».

2. **Un identifiant venu du dehors est une donnee, jamais une consigne.** Un
   client peut proposer son `X-Request-ID` — c'est ce qui permet de recoller une
   trace cote client. Il est donc **valide avant d'etre adopte**
   (`identifiant_acceptable`) : sans cela, un appelant ecrirait ce qu'il veut
   dans le journal et dans les logs, retours a la ligne compris, et une ligne
   de journal falsifiee est indiscernable d'une vraie.
"""
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

#: Le nom de l'en-tete HTTP, a l'entree comme a la sortie. `X-Request-ID` est la
#: convention la plus repandue ; en inventer une autre obligerait chaque outil
#: exterieur a apprendre la notre.
ENTETE = "X-Request-ID"

#: Longueur maximale acceptee d'un identifiant propose par un client. 64
#: caracteres couvrent un UUID sans tirets (32), un UUID avec (36) et les
#: identifiants de trace usuels ; au-dela, c'est du texte, pas un identifiant.
LONGUEUR_MAX = 64

#: Ce qu'un identifiant a le droit de contenir. Volontairement etroit : lettres,
#: chiffres, tiret, souligne. Pas d'espace, pas de retour a la ligne, pas de
#: ponctuation — c'est ce qui empeche d'ecrire une fausse ligne dans un journal
#: en faisant passer un `\n` pour la fin d'un enregistrement.
_ACCEPTABLE = re.compile(r"\A[A-Za-z0-9_-]{1,%d}\Z" % LONGUEUR_MAX)

_fil: ContextVar[Optional[str]] = ContextVar("fil_de_demande", default=None)

#: Le type de tache en cours — l'intention calculee par `analyze_intent`. Meme
#: mecanisme et meme raison que le fil ci-dessus : le routeur de modeles est un
#: `ModelProvider` dont l'interface est `generate(prompt)`, et y ajouter un
#: parametre toucherait les quatre fournisseurs et tous leurs appelants pour une
#: information qui ne change aucun comportement — elle ne fait que se mesurer.
_type_tache: ContextVar[Optional[str]] = ContextVar("type_de_tache", default=None)

#: Le plan en cours d'execution, quand il y en a un. Meme mecanisme que les deux
#: au-dessus, et pour la meme raison : une action declenchee par une etape de
#: plan doit pouvoir nommer ce plan sans qu'on ait fait descendre un parametre
#: a travers `Coordination`, `Etape` et chaque connecteur.
_plan: ContextVar[Optional[str]] = ContextVar("plan_en_cours", default=None)

#: Combien de souvenirs la recuperation a rendus depuis le debut du bloc
#: courant. Une LISTE d'un seul entier plutot qu'un entier : un `ContextVar`
#: pose une valeur, il ne l'incremente pas — et reposer une valeur incrementee
#: depuis une tache fille ne remonterait pas a la tache mere, qui est justement
#: celle qui lit le total a la fin du plan.
_souvenirs_lus: ContextVar[Optional[list]] = ContextVar("souvenirs_lus", default=None)


def identifiant_acceptable(propose: Optional[str]) -> bool:
    """Un identifiant propose de l'exterieur peut-il etre adopte tel quel ?

    Args:
        propose: la valeur recue, ou None.

    Returns:
        Vrai si elle tient dans la forme etroite acceptee. Faux sinon — et
        l'appelant en genere alors un, plutot que de refuser la demande : un
        en-tete mal forme n'est pas une raison de ne pas servir quelqu'un.
    """
    return bool(propose) and bool(_ACCEPTABLE.match(propose))


def nouvel_identifiant() -> str:
    """Un identifiant neuf, en hexadecimal, sans tiret."""
    return uuid.uuid4().hex


@contextmanager
def nouveau_fil(propose: Optional[str] = None) -> Iterator[str]:
    """Pose le fil de la demande pour la duree du bloc.

    Args:
        propose: l'identifiant venu du client, s'il en a fourni un. Il n'est
            adopte que s'il passe `identifiant_acceptable` ; sinon un
            identifiant est genere, et la demande est servie normalement.

    Yields:
        L'identifiant reellement retenu — celui qui sera rendu au client dans
        l'en-tete de reponse, et ecrit dans le journal.
    """
    identifiant = propose if identifiant_acceptable(propose) else nouvel_identifiant()
    jeton = _fil.set(identifiant)
    try:
        yield identifiant
    finally:
        # `reset` plutot que `set(None)` : un fil pose a l'interieur d'un autre
        # doit rendre le precedent, pas l'effacer.
        _fil.reset(jeton)


def fil_courant() -> Optional[str]:
    """L'identifiant de la demande en cours, ou None hors d'une demande.

    Returns:
        L'identifiant, ou `None`. Le `None` est une reponse : il dit que ce qui
        s'execute ne vient pas d'une demande HTTP — une tache de fond, un
        script, un test. Fabriquer un identifiant ici ferait apparaitre dans le
        journal des demandes qui n'ont jamais existe.
    """
    return _fil.get()


@contextmanager
def tache(type_tache: Optional[str]) -> Iterator[Optional[str]]:
    """Declare le type de tache en cours pour la duree du bloc.

    Args:
        type_tache: l'intention, telle que `analyze_intent` la rend
            (`CHAT`, `CODE_EXECUTION`, `PLAQUISTE`…). `None` est accepte : un
            appel qui ne vient d'aucune intention ne doit pas etre range sous
            une intention inventee.

    Yields:
        Le type retenu, tel quel.
    """
    jeton = _type_tache.set(type_tache)
    try:
        yield type_tache
    finally:
        _type_tache.reset(jeton)


def type_tache_courant() -> Optional[str]:
    """Le type de tache en cours, ou `None` hors d'une intention connue.

    Returns:
        L'intention, ou `None`. Le `None` est une reponse : il dit que cet
        appel ne vient d'aucune intention — un script, une tache de fond, un
        appel direct. Le ranger d'office sous `CHAT` fausserait exactement la
        statistique qu'on cherche a etablir.
    """
    return _type_tache.get()


@contextmanager
def plan(plan_id: str) -> Iterator[str]:
    """Declare le plan en cours, et remet a zero le compteur de souvenirs lus.

    Args:
        plan_id: l'identifiant de cette execution de boucle.

    Yields:
        L'identifiant, tel quel.
    """
    jeton_plan = _plan.set(plan_id)
    # Le compteur appartient au plan : le remettre a zero ICI est ce qui fait
    # que « 12 souvenirs consultes » veut dire « par ce plan », et non « depuis
    # le demarrage du serveur ».
    jeton_compteur = _souvenirs_lus.set([0])
    try:
        yield plan_id
    finally:
        _souvenirs_lus.reset(jeton_compteur)
        _plan.reset(jeton_plan)


def plan_courant() -> Optional[str]:
    """L'identifiant du plan en cours, ou `None` hors d'un plan.

    Returns:
        L'identifiant, ou `None` — une action peut tres bien avoir lieu sans
        plan (une demande simple, un script), et le dire vaut mieux que de lui
        en attribuer un.
    """
    return _plan.get()


def compter_souvenirs_lus(combien: int) -> None:
    """Ajoute au compteur de souvenirs du plan courant.

    Args:
        combien: le nombre de souvenirs qu'une recuperation vient de rendre.

    Hors d'un plan, ne fait rien : compter des lectures qui n'appartiennent a
    aucun plan gonflerait le total du plan suivant.
    """
    compteur = _souvenirs_lus.get()
    if compteur is not None and combien > 0:
        compteur[0] += combien


def souvenirs_lus() -> int:
    """Combien de souvenirs ont ete consultes depuis le debut du plan courant.

    Returns:
        Le compte, ou `0` hors d'un plan. Le zero est exact dans les deux cas :
        hors plan, aucun souvenir n'a ete compte POUR un plan.
    """
    compteur = _souvenirs_lus.get()
    return compteur[0] if compteur is not None else 0
