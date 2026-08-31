"""Lire un plan PDF, et traduire ce qu'OpenTakeoff en tire dans son langage.

`metre.py` lit des dimensions dans une phrase. Ce module lit un CHEMIN de plan
dans une phrase, et convertit ce que le connecteur OpenTakeoff en a mesure
(pieds carres, pieds lineaires — le moteur est americain) en m2 et en metres
lineaires, ses unites a lui.

**La surface d'un mur, c'est largeur x hauteur — jamais une surface au sol.**
Le propriétaire l'a corrigé lui-même (29/08/2026) : la première version de ce
module traitait « doublage »/« habillage »/« coffre » comme un plafond, en
reprenant telle quelle la liste `UNE_SEULE_FACE` de `metre.py` — fausse
équivalence. Un plafond PLAT est la seule surface verticale... non, la seule
surface dont la mesure au sol EST la mesure réelle : sa surface est, par
définition, celle du sol qu'il couvre. Un doublage, un habillage, un coffre,
une cloison ou une séparation sont posés sur un MUR : leur surface est
`largeur (la longueur du mur) x hauteur`, jamais la surface au sol de la
pièce. Un rampant suit la pente du toit — ni l'un ni l'autre : sa surface
n'est déductible d'AUCUNE mesure que ce plan donne.

**Ce que `detect_rooms` mesure, et sa limite** : le PÉRIMÈTRE ENTIER de
chaque pièce détectée — murs porteurs et murs extérieurs compris, pas
seulement les cloisons neuves à poser. Une hauteur donnée en texte permet de
calculer `perimetre x hauteur`, mais **ce périmètre reste celui de tout le
contour** : si certains de ces murs ne sont pas à poser, la longueur doit
être corrigée à la main avant de faire confiance au chiffre — c'est écrit
dans chaque réponse qui l'utilise, jamais tû.

**Trois issues, jamais quatre** :
1. plafond plat (« plafond », « faux plafond ») → surface au sol, sans hauteur ;
2. mur (doublage/habillage/coffre = 1 face ; cloison/séparation ou rien de
   nommé = 2 faces, par défaut) → périmètre mesuré x hauteur, **si une
   hauteur est donnée** ;
3. rampant, ou un mur sans hauteur donnée → **rien n'est chiffré**, les
   mesures brutes sont rendues telles quelles.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents.plaquiste.metre import NOMBRE

logger = logging.getLogger("usman.plaquiste.metre_plan")

#: OpenTakeoff mesure en pieds ; UniC Plaquiste chiffre en metres.
PIED_CARRE_EN_M2 = 0.09290304
PIED_EN_METRE = 0.3048

#: Un chemin de fichier PDF, ecrit dans une phrase — Windows (sa machine) ou
#: Linux (le serveur). `sample-plan.pdf` seul, sans dossier, n'est pas retenu :
#: sans chemin, il n'y a rien a ouvrir sur SA machine depuis une conversation.
CHEMIN_PDF = re.compile(
    r"([a-zA-Z]:[\\/][^\"'\n]+?\.pdf|(?:/[^\"'\n\s]+)+\.pdf)", re.IGNORECASE)

#: « hauteur de 2,50 m », « hauteur 2.5m », « 2,50 m de hauteur ».
HAUTEUR = re.compile(
    rf"hauteur\D{{0,6}}{NOMBRE}\s*m\b|{NOMBRE}\s*m(?:etres?)?\s+de\s+hauteur",
    re.IGNORECASE)

#: Plafond PLAT uniquement : sa surface EST la surface au sol, par
#: definition. Un rampant n'en est pas un — voir `MOTS_NON_CALCULABLES`.
MOTS_PLAFOND = ("plafond", "faux plafond")

#: Pose sur UNE seule face d'un mur. Une cloison/separation (ou rien de
#: nomme) est l'hypothese par defaut, DEUX faces — comme `metre._faces_pour`.
MOTS_UNE_FACE_MUR = ("doublage", "habillage", "coffre")

#: Nomme, mais dont la surface ne se deduit d'AUCUNE mesure de ce plan : un
#: rampant suit la pente du toit, jamais donnee par une hauteur verticale
#: ni par une surface au sol.
MOTS_NON_CALCULABLES = ("rampant",)


def chemin_dans(texte: str) -> Optional[str]:
    """Le chemin d'un plan PDF lu dans la phrase, ou None."""
    trouve = CHEMIN_PDF.search(texte or "")
    return trouve.group(1) if trouve else None


def lire_hauteur(texte: str) -> Optional[float]:
    """La hauteur sous plafond annoncee, en metres. None si rien n'est certain."""
    trouve = HAUTEUR.search(texte or "")
    if not trouve:
        return None
    brut = trouve.group(1) or trouve.group(2)
    valeur = float(brut.replace(",", "."))
    return valeur if valeur > 0 else None


def demande_un_plafond(texte: str) -> bool:
    """Vrai seulement pour un plafond PLAT : sa surface est, par definition,
    la surface au sol de la piece. Un rampant n'en est pas un."""
    minuscule = (texte or "").lower()
    return any(mot in minuscule for mot in MOTS_PLAFOND)


def demande_non_calculable_depuis_le_plan(texte: str) -> bool:
    """Vrai pour ce qu'aucune mesure de ce plan ne peut chiffrer, meme avec
    une hauteur donnee (voir `MOTS_NON_CALCULABLES`)."""
    minuscule = (texte or "").lower()
    return any(mot in minuscule for mot in MOTS_NON_CALCULABLES)


def faces_du_mur(texte: str) -> int:
    """1 face (doublage/habillage/coffre), 2 par defaut (cloison/separation)."""
    minuscule = (texte or "").lower()
    return 1 if any(mot in minuscule for mot in MOTS_UNE_FACE_MUR) else 2


def surface_murs_m2(perimetre_ml: float, hauteur_m: float) -> float:
    """Largeur (perimetre mesure) x hauteur — la formule d'un MUR, pas d'un sol.

    Le perimetre est celui de TOUT le contour de chaque piece mesuree : s'il
    inclut des murs qui ne sont pas a poser, la longueur doit etre corrigee a
    la main avant de faire confiance au chiffre — a dire dans la reponse qui
    l'utilise, jamais a taire.
    """
    return round((perimetre_ml or 0) * hauteur_m, 2)


@dataclass
class Piece:
    """Une piece mesuree, dans les unites qu'il utilise."""

    feuille: str
    numero: str
    surface_m2: float
    perimetre_ml: float
    confiance: Optional[float] = None


@dataclass
class MetrePlan:
    """Le metre d'un plan, traduit — avant tout calcul de materiaux."""

    chemin: str
    pieces: List[Piece] = field(default_factory=list)
    surface_totale_m2: float = 0.0
    perimetre_total_ml: float = 0.0
    feuilles_mesurees: List[str] = field(default_factory=list)
    feuilles_sans_echelle: List[str] = field(default_factory=list)

    @property
    def complet(self) -> bool:
        """Faux des qu'au moins une feuille n'a pas pu etre mesuree."""
        return not self.feuilles_sans_echelle


def depuis_mesure(chemin: str, detail: Dict[str, Any]) -> MetrePlan:
    """Traduit le detail rendu par `ConnecteurOpenTakeoff.mesurer` en m2/ml.

    Args:
        chemin: le chemin du plan, tel que demande.
        detail: `ResultatAction.detail` d'un appel `mesurer` reussi — le
            dictionnaire construit par `core.connectors.opentakeoff`.
    """
    pieces = [
        Piece(
            feuille=str(p.get("feuille") or ""),
            numero=str(p.get("numero") or "?"),
            surface_m2=round((p.get("surface_pi2") or 0) * PIED_CARRE_EN_M2, 2),
            perimetre_ml=round((p.get("perimetre_pi") or 0) * PIED_EN_METRE, 2),
            confiance=p.get("confiance"),
        )
        for p in (detail.get("pieces") or [])
    ]
    resume = detail.get("resume") or {}
    totaux = resume.get("totals") or {}
    surface_pi2 = totaux.get("total_sf_net")
    perimetre_pi = totaux.get("lf_net")
    return MetrePlan(
        chemin=chemin,
        pieces=pieces,
        surface_totale_m2=round((surface_pi2 or 0) * PIED_CARRE_EN_M2, 2),
        perimetre_total_ml=round((perimetre_pi or 0) * PIED_EN_METRE, 2),
        feuilles_mesurees=list(detail.get("feuilles_mesurees") or []),
        feuilles_sans_echelle=list(detail.get("feuilles_sans_echelle") or []),
    )


@dataclass
class MarquesPlan:
    """Le decompte des marques annotees d'un plan (DEC-0022) — un tag de
    menuiserie deja ecrit sur le plan, jamais un symbole devine sur l'image."""

    chemin: str
    marques: List[Dict[str, Any]] = field(default_factory=list)
    total: int = 0
    complet: bool = True
    feuilles_ignorees: List[Dict[str, Any]] = field(default_factory=list)


def depuis_marques(chemin: str, detail: Dict[str, Any]) -> MarquesPlan:
    """Traduit le detail rendu par `ConnecteurOpenTakeoff.compter_marques`.

    Args:
        chemin: le chemin du plan, tel que demande.
        detail: `ResultatAction.detail` d'un appel `compter_marques` reussi.
    """
    marques = [
        {"marque": str(m.get("mark") or ""), "compte": int(m.get("count") or 0)}
        for m in (detail.get("marques") or [])
    ]
    return MarquesPlan(
        chemin=chemin,
        marques=marques,
        total=int(detail.get("total") or 0),
        complet=bool(detail.get("complet", True)),
        feuilles_ignorees=list(detail.get("feuilles_ignorees") or []),
    )


def formater_marques(marques: MarquesPlan) -> str:
    """Un compte-rendu en francais du decompte — lisible sans reouvrir le plan."""
    if not marques.marques:
        return (f"Aucune marque annotee recensee dans {marques.chemin} : le plan "
                "n'a peut-etre pas de tableau de menuiseries, ou les tags n'y sont pas.")

    lignes = [f"Marques recensees dans {marques.chemin} :"]
    for marque in marques.marques:
        lignes.append(f"- {marque['marque']} : {marque['compte']}")
    lignes.append(f"Total : {marques.total}.")
    if not marques.complet:
        lignes.append(
            "Decompte INCOMPLET : ce total est un plancher, pas un chiffre final — "
            "certaines occurrences n'ont pas pu etre evaluees sur ce plan.")
    if marques.feuilles_ignorees:
        noms = ", ".join(str(f.get("sheet") or "?") for f in marques.feuilles_ignorees)
        lignes.append(f"Feuille(s) ignoree(s) (hors plan, sans role reconnu) : {noms}.")
    lignes.append(
        "Ce decompte lit les tags deja ecrits sur le plan (ex. un tableau de "
        "menuiseries) — il ne devine aucun symbole sur l'image.")
    return "\n".join(lignes)


def formater(metre: MetrePlan) -> str:
    """Un compte-rendu en francais, lisible sans reouvrir le plan."""
    if not metre.pieces:
        return f"Aucune piece mesurable dans {metre.chemin}."

    lignes = [f"Plan mesure ({len(metre.pieces)} piece(s), "
              f"{len(metre.feuilles_mesurees)} feuille(s) exploitable(s)) :"]
    for piece in metre.pieces:
        confiance = f", confiance {piece.confiance:.0%}" if piece.confiance is not None else ""
        lignes.append(
            f"- piece {piece.numero} ({piece.feuille}) : "
            f"{piece.surface_m2:g} m2 au sol, perimetre {piece.perimetre_ml:g} ml{confiance}")
    lignes.append(f"Total : {metre.surface_totale_m2:g} m2 au sol, "
                  f"{metre.perimetre_total_ml:g} ml de perimetre mesure.")
    if metre.feuilles_sans_echelle:
        lignes.append(
            "Feuille(s) sans echelle exploitable, donc NON comptee(s) : "
            + ", ".join(metre.feuilles_sans_echelle) + ".")
    lignes.append(
        "Le perimetre mesure est celui de CHAQUE piece entiere (murs existants "
        "compris) : ce n'est pas encore une surface de mur a chiffrer. Pour un "
        "plafond plat, la surface au sol suffit. Pour un mur (doublage, "
        "cloison, separation...), il faut une hauteur — et savoir si ce "
        "perimetre couvre bien les murs a poser. Pour un rampant, aucune "
        "mesure de ce plan ne suffit : il suit la pente du toit.")
    return "\n".join(lignes)
