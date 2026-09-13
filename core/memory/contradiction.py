"""Deux souvenirs qui ne peuvent pas etre vrais ensemble — dits, jamais arbitres.

Le defaut que ce module ferme, mesure par l'audit PHASE 0 (section F) : rien ne
remarquait que la memoire se contredisait. « Le tarif pose est 5000 F/m2 » et
« le tarif pose est 5500 F/m2 » vivaient cote a cote, tous deux `ACTIF`, tous
deux avec leur source, et la recuperation rendait celui qui gagnait au score.
Le proprietaire recevait donc un chiffre au hasard, presente avec l'assurance
d'un fait.

**Ce module enregistre le conflit et n'en resout aucun.** Deux sources qui
divergent produisent deux observations et un conflit rapporte, jamais une
moyenne et jamais un gagnant. Choisir a la place du proprietaire serait pire que se taire : un
mauvais tarif choisi par ARENA est indiscernable du bon tant qu'une facture
n'arrive pas.

**Aucun modele n'est appele.** Le verdict doit etre le meme a chaque execution,
et une contradiction annoncee par un modele serait une affirmation de plus a
verifier. La detection est donc litterale, et sa portee est etroite a dessein.

## Ce qui est detecte, et ce qui ne l'est pas

Detecte : **deux souvenirs qui parlent du meme sujet et portent des nombres
differents.** C'est la forme qui coute le plus cher ici — un prix, une surface,
un delai, un numero de devis — et c'est la seule qui se mesure sans
interpreter.

**Pas detecte, et il faut le dire plutot que de le laisser croire :** la
negation (« on travaille avec X » / « on ne travaille plus avec X »),
l'antonymie, et toute incompatibilite qui demande de comprendre la phrase.
`PORTEE` le declare, et le rapport le repete a chaque appel : un detecteur qui
laisse penser qu'il voit tout est plus dangereux que pas de detecteur du tout.

## Les quatre exclusions, et pourquoi chacune

- **`EPISODIQUE`, `TACHE` et `ERREUR` ne se contredisent pas.** « Le 4 aout,
  18 parois » et « le 5 aout, 20 parois » portent le meme sujet et des nombres
  differents : ce sont deux journees, pas un conflit. Un episode raconte un
  moment ; seuls les souvenirs qui affirment ce qui **est vrai en general**
  peuvent s'exclure — d'ou `SEMANTIQUE`, `PROCEDURALE` et `DECISION`.
- **`CONTEXTE_TEMPORAIRE` est exclu** : il est defini comme « vrai maintenant,
  faux bientot ». Deux valeurs successives sont son fonctionnement normal.
- **Un projet different n'est pas un conflit.** Deux tarifs pour deux chantiers
  sont deux tarifs. Seuls deux souvenirs du meme projet (ou tous deux sans
  projet) sont compares.
- **Un souvenir perime, rejete ou archive ne contredit rien** : il ne fait deja
  plus partie de ce qu'ARENA croit.

Un souvenir sensible dont le contenu n'a pas pu etre dechiffre est ignore lui
aussi : comparer un message d'echec fabriquerait un conflit avec le coffre.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.memory.personnelle import (
    MemoirePersonnelle,
    Nature,
    Souvenir,
    TypeSouvenir,
    est_un_echec_de_lecture,
)
from core.memory.recuperation import mots_utiles

#: La portee reelle, rendue avec chaque rapport. Elle est ecrite ici plutot que
#: laissee a la docstring parce qu'un appelant HTTP ne lit pas les docstrings.
PORTEE = (
    "Seules les divergences NUMERIQUES sur un meme sujet sont detectees "
    "(un prix, une surface, un delai, une reference). La negation et toute "
    "incompatibilite de sens ne le sont pas : elles demanderaient de comprendre "
    "la phrase, et un modele rendrait un verdict different a chaque execution."
)

#: Les types qui affirment ce qui est vrai en general. Un episode ou une tache
#: raconte un moment : deux moments qui different sont de l'histoire.
TYPES_COMPARABLES = frozenset({
    TypeSouvenir.SEMANTIQUE,
    TypeSouvenir.PROCEDURALE,
    TypeSouvenir.DECISION,
})

#: Combien de mots significatifs deux souvenirs doivent partager pour qu'on
#: considere qu'ils parlent de la meme chose. A 1, « tarif » suffirait et le
#: tarif du gypse contredirait celui de la main-d'oeuvre.
SUJET_MINIMUM = 2

#: Plafond de lecture. Comparer deux a deux coute n(n-1)/2 : la borne est ce qui
#: empeche une memoire de 50 000 souvenirs de bloquer une requete HTTP.
LIMITE_PAR_DEFAUT = 500

#: Un separateur de milliers colle deux groupes de chiffres : « 5 000 » et
#: « 5.000 » sont le meme nombre que « 5000 », et les lire comme deux nombres
#: fabriquerait un conflit entre une phrase et sa propre reecriture.
_MILLIERS = re.compile(r"(?<=\d)[\s .,](?=\d{3}(?!\d))")
_NOMBRE = re.compile(r"\d+(?:[.,]\d+)?")


def nombres(texte: str) -> Tuple[str, ...]:
    """Les nombres d'un texte, normalises, dans l'ordre d'apparition.

    Args:
        texte: le contenu d'un souvenir.

    Returns:
        Les nombres sous forme canonique — « 5 000 », « 5.000 » et « 5000 »
        rendent tous `("5000",)`, et « 5,50 » rend `("5.5",)`. Sans cette
        normalisation, une phrase reformulee se contredirait elle-meme.
    """
    trouves = []
    for brut in _NOMBRE.findall(_MILLIERS.sub("", texte)):
        valeur = brut.replace(",", ".")
        if "." in valeur:
            valeur = valeur.rstrip("0").rstrip(".")
        trouves.append(valeur.lstrip("0") or "0")
    return tuple(trouves)


def _sujet(texte: str) -> frozenset:
    """Les mots du sujet : les mots significatifs, sans les nombres.

    Les nombres sont retires parce qu'ils sont ce qui DIFFERE. Les garder dans
    le sujet ferait que deux phrases identiques a un chiffre pres ne se
    reconnaitraient plus comme parlant de la meme chose — le detecteur
    s'aveuglerait exactement sur le cas qu'il cherche.
    """
    return frozenset(mot for mot in mots_utiles(texte) if not mot.isdigit())


def _comparable(souvenir: Souvenir) -> bool:
    """Ce souvenir peut-il, par nature, en exclure un autre ?"""
    if souvenir.type not in TYPES_COMPARABLES:
        return False
    if souvenir.nature is Nature.CONTEXTE_TEMPORAIRE:
        return False
    return not est_un_echec_de_lecture(souvenir.contenu)


@dataclass(frozen=True)
class Contradiction:
    """Deux souvenirs qui ne peuvent pas etre vrais ensemble.

    Attributes:
        a: le premier souvenir, tel qu'il est en memoire.
        b: le second. Aucun des deux n'est designe comme le bon.
        sujet: les mots partages qui font dire qu'ils parlent de la meme chose.
        valeurs: les nombres de `a` puis ceux de `b`, tels que lus.
        raison: ce qui a ete constate, en une phrase.
    """

    a: Souvenir
    b: Souvenir
    sujet: Tuple[str, ...]
    valeurs: Tuple[Tuple[str, ...], Tuple[str, ...]]
    raison: str

    def to_dict(self) -> Dict[str, Any]:
        """Rendu HTTP. Les deux souvenirs sont rendus ENTIERS, avec leur source,
        leur nature et leur date : c'est ce qui permet au proprietaire de
        trancher, et trancher lui appartient."""
        return {
            "souvenirs": [self.a.to_dict(), self.b.to_dict()],
            "sujet": list(self.sujet),
            "valeurs": [list(self.valeurs[0]), list(self.valeurs[1])],
            "raison": self.raison,
            "resolue_par": None,
            "note": (
                "Aucun des deux n'est designe comme le bon. ARENA rapporte le "
                "conflit ; le trancher appartient au proprietaire."
            ),
        }


def contradictions(
    memoire: MemoirePersonnelle,
    projet: Optional[str] = None,
    limite: int = LIMITE_PAR_DEFAUT,
) -> List[Contradiction]:
    """Les conflits numeriques presents dans la memoire active.

    Args:
        memoire: la memoire personnelle a examiner.
        projet: restreint a un projet. Sans lui, tous les projets sont lus, mais
            deux souvenirs de projets DIFFERENTS ne sont jamais compares.
        limite: combien de souvenirs sont lus au plus.

    Returns:
        Les contradictions trouvees, dans l'ordre de lecture. Liste vide quand
        il n'y en a pas — ce qui ne veut pas dire que la memoire est coherente,
        seulement qu'aucun conflit **numerique** n'a ete vu (`PORTEE`).
    """
    lus = [s for s in memoire.souvenirs(projet=projet, limite=limite) if _comparable(s)]

    prepares = [(s, _sujet(s.contenu), nombres(s.contenu)) for s in lus]
    trouvees: List[Contradiction] = []

    for indice, (a, sujet_a, nombres_a) in enumerate(prepares):
        if not nombres_a:
            continue
        for b, sujet_b, nombres_b in prepares[indice + 1:]:
            if not nombres_b or a.projet != b.projet:
                continue
            commun = sujet_a & sujet_b
            if len(commun) < SUJET_MINIMUM:
                continue
            if set(nombres_a) == set(nombres_b):
                continue
            # Ce qui DIFFERE, pas tout ce qui est present. « 5000 F/m2 » contre
            # « 5500 F/m2 » partagent le « 2 » de m2 : le mettre dans la phrase
            # ferait chercher au proprietaire ce qui a change dans un nombre qui
            # n'a pas bouge. Les listes completes restent dans `valeurs`.
            propres_a = tuple(n for n in nombres_a if n not in set(nombres_b))
            propres_b = tuple(n for n in nombres_b if n not in set(nombres_a))
            trouvees.append(Contradiction(
                a=a, b=b, sujet=tuple(sorted(commun)),
                valeurs=(nombres_a, nombres_b),
                raison=(
                    f"Meme sujet ({', '.join(sorted(commun))}) et nombres "
                    f"differents : {', '.join(propres_a) or 'aucun'} contre "
                    f"{', '.join(propres_b) or 'aucun'}."
                ),
            ))
    return trouvees


def rapport(
    memoire: MemoirePersonnelle,
    projet: Optional[str] = None,
    limite: int = LIMITE_PAR_DEFAUT,
) -> Dict[str, Any]:
    """Le rapport complet, portee incluse.

    Returns:
        Les contradictions, leur nombre, et `PORTEE`. La portee accompagne
        TOUJOURS le resultat : « 0 contradiction » sans elle se lit « la memoire
        est coherente », ce qui n'a pas ete mesure.
    """
    trouvees = contradictions(memoire, projet=projet, limite=limite)
    return {
        "contradictions": [c.to_dict() for c in trouvees],
        "total": len(trouvees),
        "portee": PORTEE,
        "souvenirs_examines": len(
            [s for s in memoire.souvenirs(projet=projet, limite=limite) if _comparable(s)]
        ),
        "note": (
            "Zero contradiction ne veut pas dire que la memoire est coherente : "
            "seulement qu'aucun conflit numerique n'a ete vu."
        ),
    }
