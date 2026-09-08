"""Lire un fichier IFC avec IfcOpenShell — un moteur BIM, jamais un second.

Demande directe du proprietaire (mission BIM/metre/securite chantier,
05/09/2026) : donner a UniC Plaquiste une vraie comprehension d'un fichier
IFC (niveaux, murs, portes, fenetres, espaces, materiaux, quantites), au
lieu du seul metre par plan PDF (OpenTakeoff, `core/connectors/opentakeoff.py`)
deja en place. Les deux restent complementaires, jamais confondus : un plan
PDF est mesure en 2D par detection de pieces ; un fichier IFC est LU — ses
elements et leurs quantites sont deja dans le fichier, ils ne se mesurent pas.

**IfcOpenShell (IfcOpenShell/IfcOpenShell, LGPL-3.0-or-later) est une
dependance de bibliotheque, jamais du code copie.** Ce module n'importe et
n'appelle que son API Python publique (`ifcopenshell.open`,
`ifcopenshell.util.element`) ; aucune de ses lignes n'entre dans ce fichier.
L'obligation LGPL (le code de la bibliotheque doit rester remplacable) est
tenue par construction : c'est un paquet PyPI installe tel quel
(`pip install ifcopenshell`), jamais vendoree dans ce depot.

**Ce que ce module NE fait PAS, et pourquoi c'est ecrit ici plutot que
tu :** la surface d'un mur vient UNIQUEMENT des quantites deja calculees et
ecrites dans le fichier IFC lui-meme (`Qto_WallBaseQuantities`, ou tout jeu
de quantites portant `NetSideArea`/`GrossSideArea`/`Area`). Aucune geometrie
n'est reconstruite ici (pas de maillage, pas de moteur de forme) : un
exportateur qui n'ecrit pas ces quantites rend un mur SANS surface
exploitable, jamais une estimation calculee a partir du maillage. Le mandat
du proprietaire le dit lui-meme : « lorsque les donnees geometriques le
permettent » — un fichier qui ne les donne pas se rapporte tel quel.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    import ifcopenshell

logger = logging.getLogger("usman.production.ifc_lecture")

#: Le mot francais que la conversation utilise, vers le type IFC qu'il designe.
#: "plafond" ne couvre que les elements explicitement marques CEILING
#: (IfcCovering) : un IfcSlab peut tout aussi bien etre un plancher ou une
#: toiture, et le confondre avec un plafond produirait un compte faux plutot
#: qu'un compte absent.
TYPES_IFC: Dict[str, str] = {
    "niveau": "IfcBuildingStorey",
    "mur": "IfcWall",
    "porte": "IfcDoor",
    "fenetre": "IfcWindow",
    "espace": "IfcSpace",
    "plafond": "IfcCovering",
}

#: Les cles de quantite qui designent une surface, dans l'ordre de preference
#: (une face du mur d'abord — c'est la convention deja utilisee par
#: `agents/plaquiste/calcul_materiaux.py`, qui double lui-meme pour une
#: cloison fermee des deux cotes).
CLES_SURFACE = ("NetSideArea", "GrossSideArea", "NetArea", "GrossArea", "Area")
CLES_LONGUEUR = ("Length", "NetLength", "GrossLength")


@dataclass(frozen=True)
class ElementIfc:
    """Un element BIM, tel que le fichier le decrit — rien n'est devine."""

    guid: str
    type_ifc: str
    nom: str
    niveau: Optional[str]
    materiau: Optional[str]
    surface_m2: Optional[float]
    longueur_m: Optional[float]


def ouvrir(chemin: str) -> "ifcopenshell.file":
    """Ouvre un fichier IFC. `ImportError` si IfcOpenShell n'est pas installe.

    Import local, jamais en tete de module : la meme regle que
    `core/production/txtai_recherche.py` (DEC-0051) apres la panne mesuree
    le 05/09/2026 — une bibliotheque optionnelle importee en tete de fichier
    fait planter TOUT ARENA au demarrage des qu'elle manque, puisque chaque
    module cascade par `apps/backend/runtime.py`.
    """
    import ifcopenshell  # local : NON_CONFIGURE si absent, jamais un demarrage casse
    return ifcopenshell.open(chemin)


def _niveau_de(element: Any) -> Optional[str]:
    """Le nom du niveau (IfcBuildingStorey) qui contient l'element, ou None."""
    import ifcopenshell.util.element as util_element
    try:
        conteneur = util_element.get_container(element)
    except Exception:  # noqa: BLE001 — un conteneur illisible reste None, jamais une erreur qui casse le comptage
        return None
    if conteneur is None:
        return None
    nom = getattr(conteneur, "Name", None)
    return str(nom) if nom else None


def _materiau_de(element: Any) -> Optional[str]:
    """Le nom du materiau principal de l'element, best-effort.

    `get_material` peut rendre un ensemble de couches sans nom propre — dans
    ce cas, `None` : un materiau non identifiable ne se remplace pas par un
    nom invente.
    """
    import ifcopenshell.util.element as util_element
    try:
        materiau = util_element.get_material(element)
    except Exception:  # noqa: BLE001 — un materiau illisible reste None
        return None
    if materiau is None:
        return None
    nom = getattr(materiau, "Name", None)
    return str(nom) if nom else None


def _quantites_de(element: Any) -> Dict[str, float]:
    """Les quantites numeriques deja ecrites dans le fichier pour cet element."""
    import ifcopenshell.util.element as util_element
    try:
        jeux = util_element.get_psets(element, qtos_only=True)
    except Exception:  # noqa: BLE001 — des quantites illisibles rendent {}, jamais une erreur
        return {}
    fusion: Dict[str, float] = {}
    for jeu in jeux.values():
        if not isinstance(jeu, dict):
            continue
        for cle, valeur in jeu.items():
            if isinstance(valeur, (int, float)) and cle != "id":
                fusion[cle] = float(valeur)
    return fusion


def _premiere_cle(quantites: Dict[str, float], cles: tuple) -> Optional[float]:
    for cle in cles:
        if cle in quantites:
            return quantites[cle]
    return None


def niveaux(fichier: "ifcopenshell.file") -> List[str]:
    """Le nom de chaque niveau (IfcBuildingStorey) du fichier."""
    return [str(getattr(e, "Name", None) or e.GlobalId)
            for e in fichier.by_type("IfcBuildingStorey")]


def elements(fichier: "ifcopenshell.file", type_ifc: str,
             niveau: Optional[str] = None) -> List[ElementIfc]:
    """Tous les elements d'un type IFC, filtres par niveau si donne.

    Args:
        fichier: le fichier ouvert par `ouvrir()`.
        type_ifc: un nom de classe IFC (ex. "IfcWall") — inclut ses
            sous-types (IfcWallStandardCase est un IfcWall).
        niveau: un nom de niveau, compare sans tenir compte de la casse.
            `None` ne filtre rien.
    """
    resultats: List[ElementIfc] = []
    filtre = niveau.strip().lower() if niveau else None
    for entite in fichier.by_type(type_ifc):
        niveau_element = _niveau_de(entite)
        if filtre is not None and (niveau_element or "").strip().lower() != filtre:
            continue
        quantites = _quantites_de(entite)
        resultats.append(ElementIfc(
            guid=str(entite.GlobalId),
            type_ifc=type_ifc,
            nom=str(getattr(entite, "Name", None) or entite.GlobalId),
            niveau=niveau_element,
            materiau=_materiau_de(entite),
            surface_m2=_premiere_cle(quantites, CLES_SURFACE),
            longueur_m=_premiere_cle(quantites, CLES_LONGUEUR),
        ))
    return resultats


def surface_totale(elements_murs: List[ElementIfc]) -> Dict[str, Any]:
    """Somme la surface des murs qui en portent une ; separe ceux qui n'en ont pas.

    Jamais une estimation pour un mur sans quantite exploitable : il est
    nomme dans `elements_sans_quantite`, absent du total.
    """
    connus = [e for e in elements_murs if e.surface_m2 is not None]
    inconnus = [e.nom for e in elements_murs if e.surface_m2 is None]
    return {
        "surface_m2": round(sum(e.surface_m2 for e in connus), 4),
        "elements_chiffres": len(connus),
        "elements_sans_quantite": inconnus,
    }
