"""Choisir la methode — et surtout, choisir d'en appliquer le moins possible.

Le risque de ce genre de systeme n'est pas de manquer un specialiste : c'est
d'en convoquer six pour une question qui n'en demandait aucun. Chaque methode
ajoutee allonge le prompt, dilue la consigne et coute des jetons au
proprietaire.

**Trois regles :**

1. **Zero est une reponse.** « Bonjour », « quelle heure est-il » n'appellent
   aucune methode. Le catalogue ne s'impose pas, il repond a un besoin.

2. **Deux au maximum.** Une demande vraiment multi-domaines existe (« ameliore
   le SEO de mon site ») ; une demande a six domaines n'existe pas, c'est une
   selection trop large. Le plafond est une contrainte, pas une preference.

3. **Le mot compte, la position aussi.** Une demande qui NOMME un domaine pese
   plus qu'une qui l'effleure. Le classement est deterministe : aucun appel de
   modele n'est necessaire pour savoir que « audit de securite » appelle la
   securite, et un aiguillage qui depend d'Ollama ne marche pas quand Ollama
   est eteint.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence

from core.specialistes.catalogue import CATALOGUE, Specialiste

#: Le plafond de la regle 2. Au-dela, ce n'est plus une methode, c'est un
#: sommaire.
MAXIMUM = 2

#: Ce qu'une intention de l'aiguilleur dit deja du domaine. Sert de coup de
#: pouce : « corrige ce bug » n'a aucun mot de methode, mais l'intention
#: `SWE_FIX` sait qu'on parle de code.
RENFORT_PAR_INTENTION: Dict[str, str] = {
    "SWE_FIX": "tests",
    "REPO_ENGINEERING": "architecture",
    "CODE_EXECUTION": "tests",
    "DEEP_RESEARCH": "recherche",
    "FRESH_INFO": "recherche",
    "SOCIAL": "contenu",
    "PLAQUISTE": "affaires",
    "MONTAGE": "media",
    "AUDIO": "media",
    "VIDEO_ANALYSIS": "media",
    "STUDIO": "media",
    "TREND_SEARCH": "recherche",
    "BROWSER": "recherche",
    "RAG_DOCS": "documents",
    "GRAPHRAG": "documents",
}

#: Deux intentions restent VOLONTAIREMENT sans methode : `EMAIL` et `VISION`.
#: Leurs agents portent deja leur propre discipline — le courrier ne part
#: jamais sans confirmation et ne quitte pas la machine quand il est sensible ;
#: une image est une donnee, jamais une instruction. Leur ajouter une methode
#: generique doublerait une regle plus forte que ce qu'on ecrirait ici.
SANS_METHODE_DELIBEREMENT = ("EMAIL", "VISION")


def _sans_accents(texte: str) -> str:
    """Le texte en minuscules, accents retires — « sécurité » == « securite »."""
    decompose = unicodedata.normalize("NFD", (texte or "").lower())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def _reconnait(mot_normalise: str, texte_normalise: str) -> bool:
    """Le mot apparait-il comme un MOT, et pas au milieu d'un autre ?

    La recherche par sous-chaine se trompe vite et en silence : « ci »
    (deploiement) est contenu dans « merci », et « bonjour, merci » convoquait
    donc un specialiste DevOps. Trouve par les tests de ce module le
    01/09/2026 — c'est exactement le genre de faux positif qu'on ne remarque
    jamais, parce qu'il ne casse rien : il gonfle seulement le prompt.
    """
    return re.search(rf"(?<![a-z0-9]){re.escape(mot_normalise)}(?![a-z0-9])",
                     texte_normalise) is not None


def _poids(specialiste: Specialiste, texte_normalise: str) -> int:
    """Combien cette demande appelle cette methode.

    Un mot long compte plus qu'un mot court : « vulnerabilite » designe la
    securite, « test » peut apparaitre partout. Le poids est la longueur du
    mot reconnu, ce qui suffit a trier sans table de scores a maintenir.
    """
    total = 0
    for mot in specialiste.quand:
        normalise = _sans_accents(mot)
        if normalise and _reconnait(normalise, texte_normalise):
            total += len(normalise)
    return total


def choisir(
    demande: str,
    intention: Optional[str] = None,
    maximum: int = MAXIMUM,
) -> List[Specialiste]:
    """Les methodes que cette demande appelle vraiment — souvent aucune.

    Args:
        demande: la phrase du proprietaire, telle qu'il l'a ecrite.
        intention: l'intention deja calculee par l'aiguilleur, si elle existe.
        maximum: le plafond (regle 2).

    Returns:
        De zero a `maximum` specialistes, du plus appele au moins appele.
    """
    texte = _sans_accents(demande)
    if not texte.strip():
        return []

    scores = [(s, _poids(s, texte)) for s in CATALOGUE]
    retenus = [(s, p) for s, p in scores if p > 0]

    renfort = RENFORT_PAR_INTENTION.get(intention or "")
    if renfort and not any(s.identifiant == renfort for s, _ in retenus):
        # Le renfort entre en dernier : il complete une lecture des mots, il
        # ne la remplace pas. Poids 1, donc toujours derriere un vrai mot.
        for specialiste in CATALOGUE:
            if specialiste.identifiant == renfort:
                retenus.append((specialiste, 1))
                break

    retenus.sort(key=lambda couple: (-couple[1], couple[0].identifiant))
    return [s for s, _ in retenus[:maximum]]


def bloc_de_methode(specialistes: Sequence[Specialiste]) -> str:
    """Le bloc a poser dans le prompt systeme, ou une chaine vide.

    Vide quand aucune methode ne s'applique : un bloc « aucun specialiste »
    serait du bruit dans chaque prompt.

    L'ordre interne compte. La methode d'abord (ce qu'on fait), les controles
    ensuite (ce qu'on regarde), la definition de fini en dernier — c'est elle
    qu'on relit avant de conclure.
    """
    if not specialistes:
        return ""

    morceaux: List[str] = [
        "MÉTHODE DE SPÉCIALISTE À APPLIQUER",
        "Tu restes ARENA. Ce qui suit n'est pas un personnage : c'est la façon "
        "de travailler du métier concerné, et la liste de ce que tu vérifies "
        "avant de dire que c'est fini.",
    ]
    for specialiste in specialistes:
        morceaux.append(f"\n## {specialiste.domaine}")
        morceaux.append("Comment procéder :")
        morceaux.extend(f"{numero}. {etape}"
                        for numero, etape in enumerate(specialiste.methode, start=1))
        morceaux.append("Ce que tu vérifies systématiquement :")
        morceaux.extend(f"- {controle}" for controle in specialiste.controles)
        morceaux.append(f"C'est fini quand : {specialiste.fini_quand}.")
    return "\n".join(morceaux)
