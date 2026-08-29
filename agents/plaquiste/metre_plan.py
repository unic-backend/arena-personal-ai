"""Lire un plan PDF, et traduire ce qu'OpenTakeoff en tire dans son langage.

`metre.py` lit des dimensions dans une phrase. Ce module lit un CHEMIN de plan
dans une phrase, et convertit ce que le connecteur OpenTakeoff en a mesure
(pieds carres, pieds lineaires — le moteur est americain) en m2 et en metres
lineaires, ses unites a lui.

**Une limite honnete, ecrite ici plutot que masquee dans un calcul silencieux** :
`detect_rooms` mesure le PERIMETRE ENTIER de chaque piece detectee — murs
porteurs et murs exterieurs compris, pas seulement les cloisons neuves a
poser. L'assimiler a une surface de cloisons a chiffrer serait un exces
d'affirmation, pas une mesure. Ce module ne le fait qu'une fois, ou
l'assimilation est sans ambiguite : la surface d'un FAUX PLAFOND est, par
definition, la surface au sol de la piece — c'est deja la convention
`faces=1` que `plaquiste_agent.py` applique a un plafond ecrit en toutes
lettres (`metre.UNE_SEULE_FACE`). Pour une cloison, ce module rend le
perimetre mesure comme une INFORMATION, jamais comme un chiffrage : le
chiffrage a besoin d'une hauteur, ET de savoir lesquels de ces murs sont
vraiment a poser — ce que le plan seul ne dit pas.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents.plaquiste.metre import NOMBRE, UNE_SEULE_FACE

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

#: Mots qui font de la surface au sol mesuree une surface exploitable sans
#: ambiguite (voir docstring du module) — les memes qu'une seule face dans
#: `metre.py`, plus la formulation la plus frequente.
MOTS_PLAFOND = UNE_SEULE_FACE + ("faux plafond",)


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
    """Vrai quand la demande nomme explicitement un plafond/doublage/rampant."""
    minuscule = (texte or "").lower()
    return any(mot in minuscule for mot in MOTS_PLAFOND)


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
        "compris) : ce n'est pas encore une surface de cloisons a chiffrer. "
        "Pour un faux plafond, la surface au sol suffit ; pour une cloison, "
        "dis quels murs sont a poser et la hauteur.")
    return "\n".join(lignes)
