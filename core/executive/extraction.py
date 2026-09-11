"""Extraction deterministe de chiffres d'affaires depuis une phrase libre.

Meme discipline que `agents/finance/finance_agent.py::extraire_actif` /
`extraire_ordre_simule` : un chiffre qui n'est pas trouve de maniere non
ambigue reste absent — jamais devine par le modele, jamais remplace par une
valeur plausible. Une decision executive qui calcule sur un chiffre invente
serait pire qu'une decision qui dit honnetement « chiffre non fourni ».

**Porte volontairement etroite.** Cette extraction couvre les formulations
usuelles d'un enonce de decision (montant total, postes de cout nommes,
echeancier en pourcentages, delai en jours) — elle ne pretend pas comprendre
n'importe quelle phrase financiere. Quand elle echoue, l'appelant marque le
champ `INCONNU`/`HYPOTHESE`, il ne bloque jamais l'analyse.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

#: Un montant : chiffres, separateurs de milliers (espace, virgule, point),
#: decimale optionnelle. Pas de capture de devise ici — elle est cherchee a
#: part, elle ne conditionne jamais la reconnaissance du nombre.
_MONTANT = r"(\d{1,3}(?:[   ,.]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"


def _vers_nombre(brut: str) -> Optional[float]:
    """Un montant ecrit `10,000,000` (anglais) ou `10 000 000`/`10.000.000`
    (francais) rend le meme nombre — jamais une confusion entre separateur de
    milliers et decimale, qui diviserait un montant par mille par erreur."""
    nettoye = brut.strip()
    # Retire tout separateur de milliers (espace, virgule ou point) SAUF le
    # dernier point/virgule s'il est suivi d'exactement 1-2 chiffres (une
    # decimale reelle, ex. "4500.50"). Heuristique volontairement prudente :
    # un montant d'affaires porte rarement plus de deux decimales.
    sans_espaces = re.sub(r"[   ]", "", nettoye)
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", sans_espaces):
        # Uniquement des groupes de 3 : ce sont des separateurs de milliers.
        sans_separateurs = re.sub(r"[,.]", "", sans_espaces)
        try:
            return float(sans_separateurs)
        except ValueError:
            return None
    try:
        return float(sans_espaces.replace(",", "."))
    except ValueError:
        return None


def extraire_montant_pres_de(texte: str, mots_cles: Tuple[str, ...], fenetre: int = 60) -> Optional[float]:
    """Le premier montant trouve a moins de `fenetre` caracteres APRES un des
    `mots_cles` (insensible a la casse) — jamais le premier nombre de tout le
    texte, qui pourrait appartenir a une autre grandeur (une date, un delai)."""
    minuscule = texte.lower()
    for mot in mots_cles:
        idx = minuscule.find(mot.lower())
        if idx == -1:
            continue
        fenetre_texte = texte[idx: idx + len(mot) + fenetre]
        trouve = re.search(_MONTANT, fenetre_texte)
        if trouve:
            valeur = _vers_nombre(trouve.group(1))
            if valeur is not None:
                return valeur
    return None


#: Motifs d'echeancier : "50% advance", "30% mid-project", "50% a la commande".
#: Le libelle s'arrete a la fin de la LIGNE (espace/tiret ordinaires
#: seulement, jamais `\s` qui engloutirait un saut de ligne et fusionnerait
#: avec la phrase suivante — bug reel trouve au test de redemarrage : "20%
#: completion\n\nDeadline: 14 days" rendait le libelle "completion\n\nDeadline").
_MOTIF_ECHEANCE = re.compile(
    r"(\d{1,3}(?:[.,]\d+)?)\s*%[ \t]*([a-zA-Zàâçéèêëîïôûùüÿñæœ \t\-]{2,40})", re.IGNORECASE)


def extraire_echeancier(texte: str) -> List[Tuple[str, float]]:
    """Les paires (libelle, pourcentage) d'un echeancier de paiement decrit
    en pourcentages — rend une liste vide si rien ne correspond, jamais un
    echeancier invente a 3 lignes egales."""
    resultats: List[Tuple[str, float]] = []
    for match in _MOTIF_ECHEANCE.finditer(texte):
        pourcent = _vers_nombre(match.group(1))
        # Une seule ligne : coupe au premier saut de ligne avant meme de
        # nettoyer les bords, au cas ou la classe de caracteres en aurait
        # tout de meme laisse passer un (fin de chaine, par exemple).
        libelle = match.group(2).split("\n", 1)[0].strip(" .,;:\t")
        if pourcent is not None and libelle:
            resultats.append((libelle[:60], pourcent))
    return resultats


#: "14 days", "14 jours", "5-day delay", "delai de 5 jours".
_MOTIF_JOURS = re.compile(r"(\d{1,4})\s*[- ]?(?:jour|jours|day|days)\b", re.IGNORECASE)


def extraire_jours_pres_de(texte: str, mots_cles: Tuple[str, ...], fenetre: int = 80) -> Optional[float]:
    """Le nombre de jours le plus PROCHE d'un mot-cle (« delai », « deadline »,
    « retard ») — jamais le premier trouve dans une fenetre fusionnee, qui
    favoriserait a tort une occurrence plus loin mais plus tot dans le texte
    (« Deadline: 14 days ... possible 5-day delay » : chercher pres de
    « delay » doit rendre 5, pas 14, meme si 14 apparait avant dans le texte
    en entier)."""
    minuscule = texte.lower()
    for mot in mots_cles:
        idx = minuscule.find(mot.lower())
        if idx == -1:
            continue
        debut = max(0, idx - fenetre)
        fin = idx + len(mot) + fenetre
        fenetre_texte = texte[debut:fin]
        centre = idx - debut  # position du mot-cle DANS la fenetre decoupee
        meilleur: Optional[float] = None
        meilleure_distance = None
        for trouve in _MOTIF_JOURS.finditer(fenetre_texte):
            valeur = _vers_nombre(trouve.group(1))
            if valeur is None:
                continue
            distance = min(abs(trouve.start() - centre), abs(trouve.end() - centre))
            if meilleure_distance is None or distance < meilleure_distance:
                meilleure_distance, meilleur = distance, valeur
        if meilleur is not None:
            return meilleur
    return None


#: Mots-cles par poste de cout usuel — extensible sans toucher les appelants.
MOTS_CLES_COUT: Dict[str, Tuple[str, ...]] = {
    "materials": ("material cost", "materials", "materiel", "materiaux", "matériaux", "materiau"),
    "labor": ("labor", "labour", "main-d'oeuvre", "main d'oeuvre", "main-d'œuvre"),
    "transport": ("transport", "logistique", "livraison"),
}

MOTS_CLES_REVENU = ("project worth", "project value", "valeur du projet",
                     "montant du projet", "montant du contrat", "contract value")

MOTS_CLES_DELAI = ("deadline", "delai", "délai", "echeance", "échéance")
MOTS_CLES_RETARD = ("retard", "delay", "delayed", "possible delay")


def extraire_scenario_projet(texte: str) -> Dict[str, object]:
    """Rassemble en un seul appel ce qu'une decision de type « accepter ce
    chantier ? » (mission §38) demande le plus souvent : revenu, couts par
    poste, echeancier, delai disponible, jours de retard possible. Chaque
    champ absent reste `None`/vide — jamais complete par une supposition."""
    revenu = extraire_montant_pres_de(texte, MOTS_CLES_REVENU)
    couts = {}
    for poste, mots in MOTS_CLES_COUT.items():
        montant = extraire_montant_pres_de(texte, mots)
        if montant is not None:
            couts[poste] = montant
    return {
        "revenu": revenu,
        "couts": couts,
        "echeancier": extraire_echeancier(texte),
        "jours_disponibles": extraire_jours_pres_de(texte, MOTS_CLES_DELAI),
        "jours_risque": extraire_jours_pres_de(texte, MOTS_CLES_RETARD),
    }
