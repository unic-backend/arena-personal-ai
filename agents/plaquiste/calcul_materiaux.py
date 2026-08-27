"""Combien de materiaux pour une surface donnee, et sur quelle hypothese.

Trois choses distinguent ce module d'une regle de trois :

1. **Les ratios sont les siens.** Ils viennent d'un chantier reel
   (`ratios_materiaux` dans `config/unic_plaquiste.yaml`), pas d'un manuel :
   chutes, habitudes de pose et casse comprises. Le fichier garde les quantites
   commandees ; c'est Python qui divise.

2. **Tout ne suit pas la surface.** Sur le chantier de reference, neuf articles
   etaient commandes a 18 exemplaires pour 18 parois — un par paroi. Les
   convertir en « par m2 » donne un chiffre faux des que les parois changent de
   taille. Les deux familles sont donc calculees separement.

3. **L'hypothese de surface est ecrite dans le resultat.** « 89 m2 » peut
   vouloir dire 89 m2 de mur (178 m2 developpes) ou 89 m2 deja developpes. Le
   calcul ne devine pas en silence : il annonce laquelle des deux lectures il a
   prise, pour qu'une erreur de lecture se voie avant le client.

Les quantites sont toujours arrondies **au-dessus** : on n'achete pas 0,4 sac.
"""
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.agent.plaquiste.materiaux")

# Absorbe la seule imprecision des flottants (234/486*486 = 234.00000000000003).
# Elle ne rattrape pas un depassement reel : au-dela, l'arrondi reste vers le haut.
PRECISION = 6


@dataclass(frozen=True)
class Besoin:
    """Un article, sa quantite arrondie au-dessus, et d'ou elle sort."""

    article: str
    quantite: int
    base: str
    quantite_exacte: float
    prix_unitaire: Optional[int] = None
    total: Optional[int] = None

    def __str__(self) -> str:
        prix = f"{self.total} FCFA" if self.total is not None else "prix a confirmer"
        return f"{self.article} : {self.quantite} ({self.base}) — {prix}"


@dataclass
class Calcul:
    """Le resultat complet : les quantites, et les hypotheses qui les produisent."""

    surface_saisie: float
    faces: int
    surface_developpee: float
    parois: int
    parois_estimees: bool
    convention: str
    besoins: List[Besoin] = field(default_factory=list)
    total_connu: int = 0
    articles_sans_prix: List[str] = field(default_factory=list)
    source: str = ""


def _arrondi_superieur(valeur: float) -> int:
    """Arrondit au-dessus, apres avoir neutralise le bruit des flottants."""
    return int(math.ceil(round(valeur, PRECISION)))


def _grille_prix(metier: Dict[str, Any]) -> Dict[str, int]:
    """Materiaux et portes reunis, comme ailleurs dans l'agent."""
    grille = dict((metier or {}).get("prix_materiaux") or {})
    grille.update((metier or {}).get("prix_portes") or {})
    return grille


def surface_developpee(surface: float, faces: int = 2, deja_developpee: bool = False) -> float:
    """Applique la regle maison : une cloison fermee des deux cotes compte double."""
    if deja_developpee:
        return float(surface)
    return float(surface) * faces


def phrase_convention(surface: float, faces: int, developpee: float, deja_developpee: bool) -> str:
    """Dit en une ligne quelle lecture de la surface a ete retenue."""
    if deja_developpee:
        return (
            f"Hypothese : les {surface:g} m2 annonces sont deja des metres carres "
            f"developpes. Aucune multiplication appliquee."
        )
    if faces == 1:
        return (
            f"Hypothese : {surface:g} m2 de mur, habilles sur une seule face "
            f"(doublage) — soit {developpee:g} m2 developpes."
        )
    return (
        f"Hypothese : {surface:g} m2 de mur, cloison fermee sur ses deux faces "
        f"— soit {surface:g} x {faces} = {developpee:g} m2 developpes. "
        f"Si les {surface:g} m2 etaient deja developpes, il faut le dire : "
        f"le resultat serait divise par {faces}."
    )


def quantites_pour(
    surface: float,
    metier: Dict[str, Any],
    faces: int = 2,
    parois: Optional[int] = None,
    deja_developpee: bool = False,
) -> Calcul:
    """Chiffre les materiaux d'un chantier a partir de sa surface.

    Args:
        surface: surface annoncee, en m2.
        metier: les connaissances metier chargees depuis le YAML.
        faces: 1 (doublage) ou 2 (cloison fermee des deux cotes).
        parois: nombre de parois, s'il est connu. Sinon il est **estime** a
            partir de la paroi de reference, et le resultat le signale.
        deja_developpee: True si la surface annoncee est deja developpee.

    Returns:
        Un `Calcul` portant les quantites et l'hypothese de lecture retenue.

    Raises:
        ValueError: surface nulle ou negative, ou nombre de faces autre que 1 ou 2.
    """
    if surface is None or surface <= 0:
        raise ValueError("La surface doit etre un nombre de m2 strictement positif.")
    if faces not in (1, 2):
        raise ValueError("Une paroi se pose sur 1 face (doublage) ou 2 (cloison fermee).")
    if parois is not None and parois <= 0:
        raise ValueError("Le nombre de parois doit etre strictement positif.")

    ratios = (metier or {}).get("ratios_materiaux") or {}
    developpee = surface_developpee(surface, faces, deja_developpee)
    convention = phrase_convention(surface, faces, developpee, deja_developpee)

    reference = float(ratios.get("reference_m2_developpe") or 0)
    paroi_reference = float(ratios.get("paroi_reference_m2_developpe") or 0)

    # Sans nombre de parois, on l'estime sur la paroi de reference — et on le dit.
    parois_estimees = parois is None
    if parois is None:
        parois = _arrondi_superieur(developpee / paroi_reference) if paroi_reference > 0 else 0

    calcul = Calcul(
        surface_saisie=float(surface),
        faces=faces,
        surface_developpee=developpee,
        parois=parois,
        parois_estimees=parois_estimees,
        convention=convention,
        source=str(ratios.get("source") or ""),
    )

    if not ratios or reference <= 0:
        logger.warning("Aucun ratio materiaux exploitable : rien n'est chiffre.")
        return calcul

    grille = _grille_prix(metier)

    def ajouter(article: str, exacte: float, base: str) -> None:
        quantite = _arrondi_superieur(exacte)
        prix = grille.get(article)
        total = quantite * prix if prix is not None else None
        if prix is None:
            calcul.articles_sans_prix.append(article)
        else:
            calcul.total_connu += total
        calcul.besoins.append(
            Besoin(article=article, quantite=quantite, base=base,
                   quantite_exacte=exacte, prix_unitaire=prix, total=total)
        )

    for article, quantite_reference in (ratios.get("suivent_la_surface") or {}).items():
        ajouter(article, quantite_reference * developpee / reference, f"{developpee:g} m2 developpes")

    if parois > 0:
        base = f"{parois} paroi(s)" + (" estimee(s)" if parois_estimees else "")
        for article, par_paroi in (ratios.get("par_paroi") or {}).items():
            ajouter(article, par_paroi * parois, base)

    return calcul


def formater(calcul: Calcul) -> str:
    """Rend le calcul lisible : l'hypothese d'abord, les quantites ensuite."""
    if not calcul.besoins:
        return (
            f"{calcul.convention}\n"
            "Aucun ratio materiaux exploitable dans config/unic_plaquiste.yaml : "
            "je ne chiffre pas de quantites plutot que d'en inventer."
        )

    lignes = [
        "CALCUL DES MATERIAUX",
        calcul.convention,
    ]
    if calcul.parois_estimees:
        lignes.append(
            f"Nombre de parois non fourni : estime a {calcul.parois} sur la base "
            f"de la paroi de reference. Donne le nombre reel pour un chiffrage exact."
        )
    lignes += ["", "Quantites (arrondies au-dessus) :"]
    lignes += [f"- {besoin}" for besoin in calcul.besoins]

    if calcul.articles_sans_prix:
        lignes += [
            "",
            "Sans prix dans la grille, a confirmer : " + ", ".join(calcul.articles_sans_prix),
        ]
    lignes += [
        "",
        f"Total materiaux chiffres : {calcul.total_connu} FCFA"
        + (" (hors articles a confirmer)" if calcul.articles_sans_prix else ""),
    ]
    if calcul.source:
        lignes.append(f"Ratios issus de : {calcul.source}")
    return "\n".join(lignes)
