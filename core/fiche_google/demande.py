"""« Mes avis Google ? », « reponds a l'avis de Fatou : merci ! » : la phrase
qui parle de SA fiche Google, et ce qu'elle demande (DEC-0184).

Meme discipline que les sites (DEC-0182) : aucun agent, aucun modele. La
phrase devient une capacite du connecteur `fiche_google`.

Il faut une reference a SA fiche (« ma fiche », « mes avis », « avis
google », « google maps »…) : « donne-moi ton avis » n'est pas une demande sur
ses avis clients, ni « la note de Google en bourse » sur sa fiche.

Repondre se reconnait a sa forme, et le texte de la reponse est garde tel
qu'il a ete dit — accents et majuscules compris : c'est lui qui partira.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Possessives ou explicites : « google » seul ne suffit pas — « la note de
#: Google en bourse » n'est pas sa fiche.
REFERENCES = ("ma fiche", "notre fiche", "fiche google", "mes avis", "nos avis",
              "avis google", "avis de mes clients", "avis clients", "google maps",
              "ma note", "google business")

#: « reponds a l'avis de Fatou : Merci ! » — l'auteur, puis le texte.
REPONDRE_A = re.compile(
    r"r[ée]ponds?\s+(?:a|à)\s+l['’]avis\s+(?:de\s+|d['’])(?P<auteur>[^:]+?)\s*:\s*(?P<message>.+)$",
    re.IGNORECASE | re.DOTALL)
#: « reponds au dernier avis : Merci ! » — le plus recent sans reponse.
REPONDRE_AU_DERNIER = re.compile(
    r"r[ée]ponds?\s+au\s+dernier\s+avis\s*:\s*(?P<message>.+)$", re.IGNORECASE | re.DOTALL)

MOTS_AVIS = ("avis", "note", "etoile", "etoiles", "commentaire", "commentaires")
MOTS_FICHE = ("fiche", "adresse", "infos", "informations", "horaires")


@dataclass
class Demande:
    """Ce que la phrase demande : une capacite, et de quoi l'executer."""

    capacite: str
    auteur: Optional[str] = None      # pour repondre : l'auteur de l'avis vise
    message: str = ""                 # pour repondre : le texte, tel quel
    parametres: Dict[str, Any] = field(default_factory=dict)


def _normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte or "")
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return " ".join(sans_accents.lower().replace("’", "'").split()) + " "


def lire_demande(phrase: str) -> Optional[Demande]:
    """La demande sur sa fiche Google, ou None si la phrase n'en est pas une."""
    brute = (phrase or "").strip()
    reponse = REPONDRE_AU_DERNIER.search(brute)
    if reponse:
        return Demande("repondre", message=reponse.group("message").strip())
    reponse = REPONDRE_A.search(brute)
    if reponse:
        return Demande("repondre", auteur=reponse.group("auteur").strip(),
                       message=reponse.group("message").strip())

    texte = _normaliser(brute)
    if not any(reference in texte for reference in REFERENCES):
        return None
    if any(f" {mot} " in f" {texte}" for mot in MOTS_AVIS):
        return Demande("avis", parametres={"limite": 10})
    if any(mot in texte for mot in MOTS_FICHE):
        return Demande("fiche")
    return None


def choisir_avis(avis: List[Dict[str, Any]], auteur: Optional[str]) -> List[Dict[str, Any]]:
    """Les avis que vise la reponse.

    Avec un auteur : ceux dont le nom le contient (sans accents ni casse).
    Sans auteur : le plus recent qui n'a pas encore de reponse.
    Plusieurs resultats ne sont jamais departages ici : l'appelant demande.
    """
    if auteur:
        cherche = _normaliser(auteur).strip()
        return [a for a in avis if cherche and cherche in _normaliser(a.get("auteur") or "")]
    sans_reponse = [a for a in avis if not a.get("reponse")]
    sans_reponse.sort(key=lambda a: a.get("date") or "", reverse=True)
    return sans_reponse[:1]


def rendre(capacite: str, message: str, donnees: Any) -> str:
    """Le message du connecteur, puis ce qu'il a lu — liste, jamais resume."""
    lignes: List[str] = [message]
    if capacite == "fiche":
        for fiche in donnees or []:
            lignes.append(f"- {fiche.get('nom') or '?'} — {fiche.get('adresse') or '?'}, "
                          f"{fiche.get('ville') or '?'} — {fiche.get('site') or '?'}")
    elif capacite == "avis":
        for avis in donnees or []:
            etoiles = avis.get("etoiles")
            ligne = (f"- {avis.get('auteur') or 'anonyme'} · "
                     f"{f'{etoiles}/5' if etoiles is not None else '?/5'} · "
                     f"{avis.get('date') or '?'} : {avis.get('commentaire') or '(sans commentaire)'}")
            ligne += " [repondu]" if avis.get("reponse") else " [sans reponse]"
            lignes.append(ligne)
    return "\n".join(lignes)
