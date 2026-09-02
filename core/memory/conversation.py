"""Ce qui se dit dans une conversation finit enfin par etre retenu.

Defaut mesure le 02/09/2026. Le proprietaire : « il oublie ce qu'on s'est
dit ». La cause n'etait ni un reglage trop bas ni une memoire trop petite :

- `pwa_gateway` **lit** la memoire longue a chaque message
  (`recuperer_semantique`) ;
- il y **ecrit** : rien. Il ecrit dans `short_term_memory`, un journal que la
  recherche ne consulte jamais ;
- un seul endroit du projet entier appelle `MemoirePersonnelle.retenir()` —
  l'agent devis, et uniquement apres avoir mesure un plan PDF.

**Il lisait donc une memoire que la conversation ne remplissait jamais.** Au
dela des 8 derniers messages que le telephone renvoie, tout etait perdu pour
toujours. `core/memory/personnelle.py` le disait deja dans sa premiere ligne :
« au-dela, ARENA ne se souvient de rien ». Le module avait ete ecrit pour ca,
et personne ne l'avait branche.

**Ce que le proprietaire a choisi, le 02/09/2026 : tout garder.** On lui a dit
qu'une memoire remplie de bavardage retrouve moins bien ; il a maintenu. C'est
son droit et sa memoire.

Alors on garde tout — et on **pese** chaque souvenir, ce qui rend le choix
tenable au lieu de le rendre couteux. La recherche pondere l'importance
(20 % dans `recuperation.py`, 15 % dans `semantique.py`) : une salutation
retenue a 0,1 ne remontera jamais devant un tarif retenu a 0,9. Rien n'est
jete ; l'important passe devant.

**Deux regles que ce module ne franchit pas :**

1. **Ce qu'ARENA a repondu n'est jamais un `FAIT`.** Le proprietaire parle, il
   est la source ; ARENA produit du texte, et le retenir comme une verite
   etablie serait « la facon la plus discrete de fabriquer un mensonge
   durable » (`personnelle.py`). Sa reponse est retenue comme episodique et
   comme inference, jamais autrement.

2. **Rien n'est reformule.** Le contenu retenu est sa phrase, telle qu'il l'a
   ecrite. Resumer, c'est deja interpreter, et une interpretation fausse
   retenue pour toujours est pire qu'un oubli.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from core.memory.personnelle import MemoirePersonnelle, Nature, Souvenir, TypeSouvenir

logger = logging.getLogger("usman.memoire.conversation")

#: Au-dela, on retient le debut et on le dit. Un souvenir n'est pas une archive :
#: `recuperation.py` doit pouvoir en poser plusieurs dans une invite.
LONGUEUR_MAX = 600

#: Ce qu'il dit de sa facon de travailler : une regle, un tarif, une habitude.
#: Vrai apres la conversation, et vrai a la suivante.
REGLE = re.compile(
    r"\b(?:toujours|jamais|d'?habitude|en\s+general|par\s+defaut|la\s+regle"
    r"|il\s+faut\s+(?:toujours|jamais)?|on\s+(?:doit|fait)|je\s+fais\s+toujours"
    r"|mon\s+tarif|mes\s+tarifs|mes\s+prix|se\s+facture|coute|vaut)\b",
    re.IGNORECASE)

#: Un gout, une exigence. Peut changer sans avoir jamais ete faux.
PREFERENCE = re.compile(
    r"\b(?:je\s+(?:veux|voudrais|prefere|aime|deteste|n'?aime\s+pas)"
    r"|j'?aimerais|il\s+faut\s+que\s+tu|ne\s+fais\s+plus|arrete\s+de)\b",
    re.IGNORECASE)

#: Ce qui reste a faire.
TACHE = re.compile(
    r"\b(?:rappelle[- ]moi|n'?oublie\s+pas|pense\s+a|il\s+faudra|plus\s+tard"
    r"|demain|la\s+semaine\s+prochaine|a\s+faire)\b",
    re.IGNORECASE)

#: Ce qui ne dit presque rien : bonjour, merci, « ok ». Retenu quand meme —
#: c'est son choix — mais pese pour ne jamais passer devant un tarif.
BANAL = re.compile(
    r"^\W*(?:bonjour|bonsoir|salut|merci|ok|okay|oui|non|d'?accord|c'?est\s+bon"
    r"|vas[- ]?y|parfait|super|nickel|bien|ah|hein|hmm)\W*$",
    re.IGNORECASE)

#: Ce qu'on pese. Les valeurs ne sont pas des notes de qualite : ce sont des
#: rangs de rappel. Un tarif doit remonter avant un bavardage, voila tout.
IMPORTANCE_REGLE = 0.9        # un tarif, une regle de metier : ca resservira
IMPORTANCE_PREFERENCE = 0.85  # « ne fais plus ca » doit tenir
IMPORTANCE_TACHE = 0.8        # ce qui reste a faire se rappelle tout seul
IMPORTANCE_ORDINAIRE = 0.5    # le defaut de `personnelle.py`
IMPORTANCE_REPONSE = 0.3      # ce qu'ARENA a dit passe apres ce qu'il a dit
IMPORTANCE_BANAL = 0.1        # garde, jamais devant


def _tronquer(texte: str) -> str:
    """Coupe ce qui est trop long, et **le dit**. Une coupe muette se lit comme
    une phrase que le proprietaire aurait terminee ainsi."""
    texte = (texte or "").strip()
    if len(texte) <= LONGUEUR_MAX:
        return texte
    return texte[:LONGUEUR_MAX].rstrip() + " […] (message tronque)"


def classer(message: str) -> tuple[TypeSouvenir, Nature, float]:
    """Ce qu'est cette phrase, et a quel rang la rappeler.

    Deterministe : aucun modele n'est appele. La memoire doit se remplir meme
    quand Ollama est eteint — c'est justement quand il l'est que le
    proprietaire perd le plus.
    """
    texte = (message or "").strip()
    if BANAL.match(texte):
        return (TypeSouvenir.EPISODIQUE, Nature.FAIT, IMPORTANCE_BANAL)
    if TACHE.search(texte):
        return (TypeSouvenir.TACHE, Nature.FAIT, IMPORTANCE_TACHE)
    if PREFERENCE.search(texte):
        return (TypeSouvenir.SEMANTIQUE, Nature.PREFERENCE, IMPORTANCE_PREFERENCE)
    if REGLE.search(texte):
        return (TypeSouvenir.SEMANTIQUE, Nature.FAIT, IMPORTANCE_REGLE)
    return (TypeSouvenir.EPISODIQUE, Nature.FAIT, IMPORTANCE_ORDINAIRE)


def retenir_l_echange(
    memoire: Optional[MemoirePersonnelle],
    question: str,
    reponse: str,
    source: str,
    projet: Optional[str] = None,
) -> List[Souvenir]:
    """Retient ce qui vient d'etre dit. Rend les souvenirs ecrits.

    Ne leve jamais : une memoire qui casse ne doit pas emporter la reponse que
    le proprietaire attend. Elle se plaint dans les journaux et la conversation
    continue — c'est la meme regle que partout ailleurs ici.

    Args:
        memoire: la memoire longue. `None` rend une liste vide, sans bruit.
        question: ce que le proprietaire a ecrit, tel quel.
        reponse: ce qu'ARENA a repondu, tel quel.
        source: d'ou ca vient — obligatoire, `retenir()` refuse sans.
        projet: le chantier ou le client concerne, s'il est connu.
    """
    if memoire is None:
        return []

    ecrits: List[Souvenir] = []
    question = _tronquer(question)
    reponse = _tronquer(reponse)

    if question:
        type_, nature, importance = classer(question)
        try:
            ecrits.append(memoire.retenir(
                contenu=question, type=type_, nature=nature,
                source=source, projet=projet, importance=importance,
                metadonnees={"role": "proprietaire"}))
        except Exception as erreur:  # noqa: BLE001 — la reponse passe avant la memoire
            logger.warning("Question non retenue : %s", erreur)

    if reponse:
        # Jamais `FAIT` : ARENA n'atteste rien. La retenir comme une verite
        # etablie ferait, du premier chiffre approximatif, un souvenir
        # definitif que plus rien ne contredirait.
        try:
            ecrits.append(memoire.retenir(
                contenu=reponse, type=TypeSouvenir.EPISODIQUE,
                nature=Nature.INFERENCE, source=source, projet=projet,
                importance=IMPORTANCE_REPONSE,
                metadonnees={"role": "usman"}))
        except Exception as erreur:  # noqa: BLE001
            logger.warning("Reponse non retenue : %s", erreur)

    return ecrits
