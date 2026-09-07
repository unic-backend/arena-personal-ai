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

#: Les separateurs de dimensions qu'il ecrit reellement. **« sur » manquait**,
#: et c'est le plus courant a l'oral comme a l'ecrit : « 5 m sur 2,5 m ».
#: Mesure du 07/09/2026, sur sa capture d'ecran : « Fais-moi une cloison de
#: 5 m sur 2,5 m » n'etait pas lue, donc aucun calcul n'etait injecte, donc le
#: modele n'avait aucun chiffre et retombait sur les trois questions.
SEPARATEUR = r"(?:x|par|\*|×|sur)"

#: Combien de parois, ecrit en toutes lettres. « une cloison » est un compte,
#: exactement comme « 1 cloison » — et c'est ainsi qu'il parle.
COMPTE_EN_LETTRES = {
    "une": 1, "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}

#: « 18 parois de 5,40 x 2,50 m » — le cas de son devis de reference — ET
#: « une cloison de 5 m sur 2,5 m », qui ne l'etait pas.
#:
#: Le compte est desormais OPTIONNEL et peut s'ecrire en lettres. Sans compte
#: du tout (« cloison de 5 m sur 2,5 m »), c'est UNE paroi : c'est ce que la
#: phrase dit, et refuser de la lire revenait a ne rien calculer alors que
#: tout etait donne.
PAROIS_DIMENSIONNEES = re.compile(
    rf"(?:(\d+|{'|'.join(COMPTE_EN_LETTRES)})\s+)?"
    rf"(?:parois?|cloisons?|murs?|doublages?|separations?|séparations?)\s*"
    rf"(?:de\s*)?{NOMBRE}\s*(?:m\b|metres?|mètres?)?\s*"
    rf"{SEPARATEUR}\s*{NOMBRE}",
    re.IGNORECASE)

#: Ce qu'on ne plaque PAS : une porte, une fenetre, une baie. Mesure du
#: 07/09/2026 : **aucun module du depot ne deduisait une ouverture**, donc une
#: cloison avec une porte etait chiffree comme une cloison pleine — plus de
#: plaques, plus de vis, plus d'enduit, et un prix trop haut.
OUVERTURES = re.compile(
    rf"(?:(\d+|{'|'.join(COMPTE_EN_LETTRES)})\s+)?"
    rf"(portes?|fen[êe]tres?|baies?|ouvertures?|tr[ée]mies?)\s*"
    rf"(?:de\s*)?{NOMBRE}\s*(?:(cm|centim[èe]tres?|m|metres?|mètres?)\s*)?"
    rf"{SEPARATEUR}\s*{NOMBRE}\s*(cm|centim[èe]tres?|m\b|metres?|mètres?)?",
    re.IGNORECASE)


def _en_metres(valeur: float, unite: str) -> float:
    """Une cote en metres, quelle que soit l'unite ecrite.

    L'unite est prise telle qu'elle est ecrite quand elle l'est. Sans unite,
    la regle est celle du bon sens du metier : **une ouverture ne fait jamais
    80 metres**. Au-dela de 10, le nombre est donc lu en centimetres — c'est
    ainsi qu'il ecrit les portes (« 80 x 210 »), et cette lecture est dite
    dans le champ `lu` pour qu'il puisse la dementir d'un coup d'oeil.
    """
    if unite and unite.lower().startswith(("cm", "centim")):
        return valeur / 100.0
    if unite:
        return valeur
    return valeur / 100.0 if valeur > 10 else valeur


def lire_ouvertures(texte: str) -> tuple:
    """La surface a NE PAS plaquer, et la phrase qui la justifie.

    Returns:
        `(surface_m2, description)`. `(0.0, "")` quand la phrase n'en nomme
        aucune — un texte sans porte n'est pas une porte de surface nulle.
    """
    total, dits = 0.0, []
    for trouve in OUVERTURES.finditer(texte or ""):
        brut_compte, nom, larg, unite_l, haut, unite_h = trouve.groups()
        compte = 1
        if brut_compte:
            compte = (int(brut_compte) if brut_compte.isdigit()
                      else COMPTE_EN_LETTRES.get(brut_compte.lower(), 1))
        unite = unite_h or unite_l or ""
        largeur = _en_metres(_nombre(larg), unite)
        hauteur = _en_metres(_nombre(haut), unite)
        if largeur <= 0 or hauteur <= 0:
            continue
        surface = compte * largeur * hauteur
        total += surface
        etiquette = nom.lower().rstrip("s")
        dits.append(f"{compte} {etiquette}{'s' if compte > 1 else ''} "
                    f"de {largeur:g} x {hauteur:g} m = {surface:g} m2")
    return round(total, 3), " ; ".join(dits)

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
    #: Surface des ouvertures DEJA retiree de `surface`. Zero quand la phrase
    #: n'en nomme aucune — jamais une porte de surface nulle.
    ouvertures: float = 0.0


def _faces_pour(texte: str) -> int:
    """Une face pour un doublage ou un plafond, deux pour une cloison fermee."""
    return 1 if any(mot in texte.lower() for mot in UNE_SEULE_FACE) else 2


def _sans_les_creux(brute: float, creux: float, dit_creux: str) -> tuple:
    """La surface a plaquer, ce qui a ete deduit, et la phrase qui le dit.

    Une porte plus grande que le mur n'existe pas ; si les cotes disent le
    contraire, c'est la LECTURE qui est fausse, pas le chantier. La surface
    brute est alors gardee telle quelle — mieux vaut un metre trop haut,
    visible et discutable, qu'une surface negative qui ferait tomber le calcul
    ou, pire, un zero qui passerait pour une mesure.

    **Et surtout, on le DIT.** Mesure du 07/09/2026 : une premiere version
    refusait bien la deduction mais annoncait quand meme « moins 1 porte de
    1,68 m2, soit 1 m2 a plaquer » — une phrase qui decrit une deduction qui
    n'a pas eu lieu. Un message qui ment sur ce qu'il a fait est pire qu'un
    calcul faux : on ne peut meme pas le corriger.

    Returns:
        `(surface, deduit, phrase)`.
    """
    if creux <= 0:
        return brute, 0.0, ""
    if creux >= brute:
        return brute, 0.0, (
            f", mais {dit_creux} — plus grand que la paroi elle-meme : "
            "rien n'a ete deduit, verifie les cotes")
    return (round(brute - creux, 3), creux,
            f", moins {dit_creux}, soit {round(brute - creux, 3):g} m2 a plaquer")


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

    creux, dit_creux = lire_ouvertures(texte)

    # 1. Le cas le plus precis : des parois AVEC leurs dimensions. Le compte
    #    est optionnel — « une cloison de 5 m sur 2,5 m » en decrit UNE, et la
    #    refuser revenait a ne rien calculer alors que tout etait donne.
    dimensionnees = PAROIS_DIMENSIONNEES.search(texte)
    if dimensionnees:
        brut_compte = dimensionnees.group(1)
        if brut_compte is None:
            parois = 1
        elif brut_compte.isdigit():
            parois = int(brut_compte)
        else:
            parois = COMPTE_EN_LETTRES.get(brut_compte.lower(), 1)
        largeur, hauteur = _nombre(dimensionnees.group(2)), _nombre(dimensionnees.group(3))
        if parois > 0 and largeur > 0 and hauteur > 0:
            brute = parois * largeur * hauteur
            surface, deduit, phrase = _sans_les_creux(brute, creux, dit_creux)
            return Demande(
                surface=surface, faces=faces, parois=parois, deja_developpee=developpee,
                ouvertures=deduit,
                lu=(f"{parois} paroi{'s' if parois > 1 else ''} de "
                    f"{largeur:g} x {hauteur:g} m = {brute:g} m2 de surface simple"
                    + phrase))

    # 2. Une surface annoncee directement.
    surface_lue = SURFACE.search(texte)
    if surface_lue:
        brute = _nombre(surface_lue.group(1))
        if brute > 0:
            compte = NOMBRE_DE_PAROIS.search(texte)
            parois = int(compte.group(1)) if compte else None
            surface, deduit, phrase = _sans_les_creux(brute, creux, dit_creux)
            return Demande(
                surface=surface, faces=faces, parois=parois, deja_developpee=developpee,
                ouvertures=deduit,
                lu=(f"{brute:g} m2 annonces"
                    + (f", {parois} parois" if parois else "") + phrase))

    logger.debug("Aucune dimension exploitable dans la demande.")
    return None
