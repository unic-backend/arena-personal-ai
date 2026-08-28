"""Lire des dimensions dans une phrase, ou se taire.

Le calculateur de materiaux existe depuis le premier jour et **personne ne
l'appelait** : mesure du 2026-08-28, `calcul_materiaux` n'etait importe que par
le script de mesures. Quand le proprietaire demandait un metre, le modele
inventait les quantites au lieu d'utiliser celles tirees de son devis reel.

Ce module est la piece manquante : il reconnait les dimensions dans une demande
en francais, pour que le calcul parte de chiffres lus et non supposes.

**Trois regles :**

1. **Ne rien reconnaitre est une reponse valide.** Sans dimensions certaines,
   `lire_demande` rend `None`, et le chiffrage n'est pas injecte. Un metre
   fabrique a partir d'un nombre mal lu est pire qu'un metre absent : il a
   l'air juste.

2. **Ce qui a ete lu est dit.** Le champ `lu` rend la lecture verifiable d'un
   coup d'oeil. Le proprietaire doit pouvoir constater que « 5,40 x 2,50 » a
   bien ete compris comme une paroi, pas comme une surface.

3. **Le nombre de faces est une hypothese, et elle est nommee.** Un doublage ou
   un plafond comptent une face ; une cloison fermee des deux cotes en compte
   deux. `Calcul.convention` porte cette hypothese jusque dans la reponse.
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("usman.plaquiste.metre")

#: Ce qui ne se compte que d'un cote : on ne double pas la surface.
UNE_SEULE_FACE = ("doublage", "plafond", "rampant", "habillage", "coffre")

#: Un nombre francais : la virgule est un separateur decimal.
NOMBRE = r"(\d+(?:[.,]\d+)?)"

#: « 18 parois de 5,40 x 2,50 m » — le cas de son devis de reference.
PAROIS_DIMENSIONNEES = re.compile(
    rf"(\d+)\s*(?:parois?|cloisons?|murs?)\s*(?:de\s*)?{NOMBRE}\s*(?:m\b|metres?)?\s*"
    rf"(?:x|par|\*|×)\s*{NOMBRE}",
    re.IGNORECASE)

#: « 120 m2 », « 45 metres carres ».
SURFACE = re.compile(
    rf"{NOMBRE}\s*(?:m²|m2|m\^2|metres?\s+carres?|mètres?\s+carrés?)",
    re.IGNORECASE)

#: « 18 parois », sans dimensions.
NOMBRE_DE_PAROIS = re.compile(r"(\d+)\s*(?:parois?|cloisons?)", re.IGNORECASE)

#: Une surface deja developpee ne se double pas une seconde fois.
DEJA_DEVELOPPEE = re.compile(r"developp|développ", re.IGNORECASE)


def _nombre(brut: str) -> float:
    return float(brut.replace(",", "."))


@dataclass(frozen=True)
class Demande:
    """Ce qui a ete lu dans la phrase, et rien de plus."""

    surface: float
    faces: int
    parois: Optional[int] = None
    deja_developpee: bool = False
    lu: str = ""


def _faces_pour(texte: str) -> int:
    """Une face pour un doublage ou un plafond, deux pour une cloison fermee."""
    return 1 if any(mot in texte.lower() for mot in UNE_SEULE_FACE) else 2


def lire_demande(texte: str) -> Optional[Demande]:
    """Rend les dimensions lues, ou `None` quand rien n'est certain.

    Args:
        texte: la demande, telle que le proprietaire l'a ecrite.

    Returns:
        La `Demande` si des dimensions exploitables ont ete reconnues. `None`
        sinon — et c'est une reponse, pas un echec.
    """
    if not (texte or "").strip():
        return None

    faces = _faces_pour(texte)
    developpee = bool(DEJA_DEVELOPPEE.search(texte))

    # 1. Le cas le plus precis : un nombre de parois AVEC leurs dimensions.
    dimensionnees = PAROIS_DIMENSIONNEES.search(texte)
    if dimensionnees:
        parois = int(dimensionnees.group(1))
        largeur, hauteur = _nombre(dimensionnees.group(2)), _nombre(dimensionnees.group(3))
        if parois > 0 and largeur > 0 and hauteur > 0:
            surface = parois * largeur * hauteur
            return Demande(
                surface=surface, faces=faces, parois=parois, deja_developpee=developpee,
                lu=(f"{parois} parois de {largeur:g} x {hauteur:g} m "
                    f"= {surface:g} m2 de surface simple"))

    # 2. Une surface annoncee directement.
    surface_lue = SURFACE.search(texte)
    if surface_lue:
        surface = _nombre(surface_lue.group(1))
        if surface > 0:
            compte = NOMBRE_DE_PAROIS.search(texte)
            parois = int(compte.group(1)) if compte else None
            return Demande(
                surface=surface, faces=faces, parois=parois, deja_developpee=developpee,
                lu=f"{surface:g} m2 annonces" + (f", {parois} parois" if parois else ""))

    logger.debug("Aucune dimension exploitable dans la demande.")
    return None
