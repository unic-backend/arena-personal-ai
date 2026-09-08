"""Lire un chemin de fichier IFC dans une phrase, et traduire ce que le
connecteur IFC en tire dans son langage — meme forme que `metre_plan.py`
pour les plans PDF (OpenTakeoff), jamais fondue avec lui : un plan PDF est
MESURE en 2D, un fichier IFC est LU, ses quantites sont deja dedans.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Un chemin de fichier IFC, ecrit dans une phrase — Windows (sa machine) ou
#: Linux (le serveur). Meme forme que `metre_plan.CHEMIN_PDF`.
CHEMIN_IFC = re.compile(
    r"([a-zA-Z]:[\\/][^\"'\n]+?\.ifc|(?:/[^\"'\n\s]+)+\.ifc)", re.IGNORECASE)


def chemin_dans(texte: str) -> Optional[str]:
    """Le chemin d'un fichier IFC lu dans la phrase, ou None."""
    trouve = CHEMIN_IFC.search(texte or "")
    return trouve.group(1) if trouve else None


@dataclass
class AnalyseIfc:
    """Ce que `ConnecteurIfc.analyser` rend, traduit — niveaux et comptes."""

    chemin: str
    niveaux: List[str] = field(default_factory=list)
    comptes: Dict[str, int] = field(default_factory=dict)
    elements_par_niveau: Dict[str, Dict[str, int]] = field(default_factory=dict)


def depuis_analyse(chemin: str, detail: Dict[str, Any]) -> AnalyseIfc:
    return AnalyseIfc(
        chemin=chemin,
        niveaux=list(detail.get("niveaux") or []),
        comptes=dict(detail.get("comptes") or {}),
        elements_par_niveau={k: dict(v) for k, v in (detail.get("elements_par_niveau") or {}).items()},
    )


def formater_analyse(analyse: AnalyseIfc) -> str:
    """Un compte-rendu en francais, lisible sans reouvrir le fichier."""
    if not analyse.niveaux and not any(analyse.comptes.values()):
        return (f"Le fichier {analyse.chemin} ne contient aucun element BIM reconnu "
                "(mur, porte, fenetre, espace, plafond).")

    lignes = [f"Fichier IFC {analyse.chemin} :"]
    if analyse.niveaux:
        lignes.append("Niveaux : " + ", ".join(analyse.niveaux) + ".")
    lignes += [f"- {mot} : {n}" for mot, n in sorted(analyse.comptes.items())]
    if analyse.elements_par_niveau:
        lignes.append("Par niveau :")
        for niveau, comptes in analyse.elements_par_niveau.items():
            detail = ", ".join(f"{n} {mot}(s)" for mot, n in sorted(comptes.items()))
            lignes.append(f"  - {niveau} : {detail}")
    return "\n".join(lignes)


@dataclass
class MetreIfc:
    """La surface des murs, telle que le fichier IFC la donne — une face."""

    chemin: str
    surface_m2: float = 0.0
    murs: int = 0
    elements_chiffres: int = 0
    elements_sans_quantite: List[str] = field(default_factory=list)


def depuis_metre(chemin: str, detail: Dict[str, Any]) -> MetreIfc:
    return MetreIfc(
        chemin=chemin,
        surface_m2=float(detail.get("surface_m2") or 0),
        murs=int(detail.get("murs") or 0),
        elements_chiffres=int(detail.get("elements_chiffres") or 0),
        elements_sans_quantite=list(detail.get("elements_sans_quantite") or []),
    )


#: Une demande de croquis IFC — GENERER un fichier, jamais confondu avec
#: lire un fichier IFC existant (`chemin_dans` ci-dessus). Phrase exacte,
#: jamais le mot « ifc » seul : il apparaît aussi dans « analyse ce fichier
#: ifc », qui ne doit jamais produire un fichier de son propre chef.
DEMANDE_DE_CROQUIS_IFC = re.compile(
    r"g[ée]n[èe]re\w* (?:le|un|moi) (?:croquis|fichier) ifc"
    r"|cr[ée]e\w* (?:le|un|moi) (?:croquis|fichier) ifc"
    r"|fais\w* (?:le|un|moi) (?:croquis|fichier) ifc"
    r"|exporte\w*.{0,30}\bifc\b",
    re.IGNORECASE)

#: « 5,40 x 2,50 » — longueur x hauteur pour UNE cloison. Volontairement
#: séparé de `agents/plaquiste/metre.py::lire_demande` (qui compte des
#: PAROIS et rend une surface déjà multipliée, jamais longueur/hauteur
#: séparément) : générer un mur exige les deux cotes distinctes, pas leur
#: produit.
_NOMBRE_CROQUIS = r"(\d+(?:[.,]\d+)?)"
DIMENSIONS_CROQUIS = re.compile(
    rf"{_NOMBRE_CROQUIS}\s*(?:m\b|metres?|mètres?)?\s*(?:x|par|\*|×)\s*{_NOMBRE_CROQUIS}",
    re.IGNORECASE)


def demande_de_croquis_ifc(texte: str) -> bool:
    """Vrai si la demande veut GÉNÉRER un fichier IFC, pas en lire un."""
    return bool(DEMANDE_DE_CROQUIS_IFC.search(texte or ""))


def dimensions_pour_croquis(texte: str) -> Optional[Tuple[float, float]]:
    """La longueur et la hauteur lues pour un croquis, ou None si rien
    d'exploitable — jamais une dimension devinée."""
    trouve = DIMENSIONS_CROQUIS.search(texte or "")
    if not trouve:
        return None
    longueur = float(trouve.group(1).replace(",", "."))
    hauteur = float(trouve.group(2).replace(",", "."))
    if longueur <= 0 or hauteur <= 0:
        return None
    return longueur, hauteur


def formater_metre(metre: MetreIfc) -> str:
    """Un compte-rendu en francais — l'hypothese de lecture jamais tue."""
    if metre.murs == 0:
        return f"Aucun mur trouve dans {metre.chemin}."

    lignes = [
        f"{metre.murs} mur(s) dans {metre.chemin}, dont {metre.elements_chiffres} "
        f"portant une quantite exploitable : {metre.surface_m2:g} m2 chiffres.",
        "Cette surface vient des quantites DEJA CALCULEES et ecrites dans le "
        "fichier IFC (NetSideArea/GrossSideArea d'une face) — jamais une "
        "geometrie recalculee ici.",
    ]
    if metre.elements_sans_quantite:
        reste = metre.elements_sans_quantite[:10]
        suffixe = "..." if len(metre.elements_sans_quantite) > 10 else ""
        lignes.append(
            f"{len(metre.elements_sans_quantite)} mur(s) SANS quantite exploitable "
            f"dans le fichier, donc ABSENT(S) de ce total : {', '.join(reste)}{suffixe}.")
    return "\n".join(lignes)
