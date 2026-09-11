"""Choisir QUELS roles consulter — jamais tous, jamais aucun par defaut
(mission §6/§39).

Meme algorithme que `core/specialistes/selection.py` (deterministe, poids =
longueur du mot-cle reconnu comme un mot entier, pas une sous-chaine) —
**repris, pas duplique dans sa logique**, mais avec sa PROPRE table de
mots-cles (domaine des affaires, pas du code) et son propre plafond : une
decision d'affaires reelle convoque legitimement plus de deux perspectives
(l'exemple meme de la mission §38 — accepter un chantier — appelle finance,
operations, risque ET approvisionnement/contrat).

**Zero est une reponse.** Une question qui ne nomme aucun mot d'affaires
("bonjour", "quelle heure est-il") ne convoque personne : c'est alors une
question directe, pas une decision executive (§10 — le format s'adapte).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Tuple

#: Le plafond — plus large que celui du code (2) parce qu'une decision
#: d'affaires reelle est structurellement plus transverse (mission §38).
MAXIMUM = 4


@dataclass(frozen=True)
class RoleExecutif:
    """Un role que l'Executive Intelligence sait consulter."""

    identifiant: str
    domaine: str
    mots_cles: Tuple[str, ...]


#: Les roles disponibles. Chacun est adosse a une capacite REELLE d'ARENA
#: dans `core/executive/specialistes.py` — jamais un role decoratif.
#: Chaque role porte ses mots-cles en francais ET en anglais — le
#: proprietaire pose ses questions dans les deux (mission §38, dont l'enonce
#: du scenario synthetique est ecrit en anglais). Un role qui ne reconnaitrait
#: que le francais manquerait la moitie des demandes reelles.
ROLES: Tuple[RoleExecutif, ...] = (
    RoleExecutif(
        identifiant="finance",
        domaine="Finance d'affaires",
        mots_cles=(
            "marge", "rentabilite", "rentabilité", "tresorerie", "trésorerie",
            "cash flow", "cash-flow", "chiffre d'affaires", "revenu", "cout",
            "coût", "budget", "investissement", "financement", "prix de revient",
            "point mort", "break-even", "acompte", "echeancier", "échéancier",
            "paiement", "facture", "devis",
            # Anglais.
            "margin", "profitability", "profit", "revenue", "cost", "costs",
            "material cost", "labor cost", "labour cost", "transport cost",
            "budget", "investment", "financing", "payment", "advance",
            "invoice", "quote", "project worth", "project value", "price",
        ),
    ),
    RoleExecutif(
        identifiant="operations",
        domaine="Operations",
        # « chantier » n'y figure PAS — meme observation que
        # `core/specialistes/catalogue.py` (« ni devis, ni chantier, ni
        # client : ce sont les mots de TOUS les jours ») : « une video de mon
        # chantier » contiendrait sinon un mot d'operations sans etre une
        # decision d'affaires. Meme raison pour « project » cote anglais.
        mots_cles=(
            "delai", "délai", "planning", "livraison", "capacite",
            "capacité", "main-d'oeuvre", "main d'oeuvre", "effectif",
            "logistique", "processus", "faisabilite", "faisabilité",
            "deadline", "echeance", "échéance",
            # Anglais.
            "delivery", "capacity", "workforce", "labor", "labour",
            "logistics", "process", "feasibility", "feasible", "schedule",
        ),
    ),
    RoleExecutif(
        identifiant="risque",
        domaine="Risque",
        mots_cles=(
            "risque", "risques", "danger", "expose", "exposé", "exposition",
            "depend", "dépend", "dependance", "dépendance", "retard",
            "incertitude", "aleatoire", "aléatoire", "imprevisible", "imprévisible",
            # Anglais.
            "risk", "risks", "exposure", "dependency", "dependent", "delay",
            "delayed", "uncertain", "uncertainty", "unpredictable",
        ),
    ),
    RoleExecutif(
        identifiant="approvisionnement",
        domaine="Approvisionnement et contrats",
        mots_cles=(
            "fournisseur", "fournisseurs", "contrat", "sous-traitant",
            "achat", "approvisionnement", "materiaux", "matériaux",
            "commande", "clause", "condition contractuelle",
            # Anglais.
            "supplier", "suppliers", "contract", "subcontractor", "purchase",
            "procurement", "materials", "order", "clause", "contractual",
        ),
    ),
    RoleExecutif(
        identifiant="strategie_marche",
        domaine="Strategie et marche",
        mots_cles=(
            "concurrent", "concurrence", "marche", "marché", "strategie",
            "stratégie", "expansion", "acquisition client", "clientele",
            "clientèle", "positionnement", "marketing", "vente", "ventes",
            "prospection", "croissance",
            # Anglais.
            "competitor", "competition", "market", "strategy", "customer acquisition",
            "positioning", "sales", "growth",
        ),
    ),
    RoleExecutif(
        identifiant="ressources_humaines",
        domaine="Ressources humaines",
        mots_cles=(
            "embauche", "recrutement", "salarie", "salarié", "employe",
            "employé", "equipe", "équipe", "formation", "personnel",
            "ressources humaines", "rh",
            # Anglais.
            "hiring", "recruitment", "employee", "staff", "training",
            "human resources",
        ),
    ),
)


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", (texte or "").lower())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def _reconnait(mot_normalise: str, texte_normalise: str) -> bool:
    """Le mot apparait comme un MOT (ou une locution complete), pas une
    sous-chaine — meme garde-fou que `core/specialistes/selection.py`."""
    return re.search(rf"(?<![a-z0-9]){re.escape(mot_normalise)}(?![a-z0-9])",
                     texte_normalise) is not None


def _poids(role: RoleExecutif, texte_normalise: str) -> int:
    total = 0
    for mot in role.mots_cles:
        normalise = _sans_accents(mot)
        if normalise and _reconnait(normalise, texte_normalise):
            total += len(normalise)
    return total


#: Une demande d'evaluation GENERALE («donne-moi un bilan», «executive
#: assessment») ne nomme souvent AUCUN domaine precis — mission §40, dont
#: l'enonce meme est « give me an executive assessment of the current
#: business/project information ». Sans mot de domaine, `selectionner`
#: rendrait zero role alors que la question EST une decision d'affaires
#: (elle n'atteint ce module qu'apres que l'aiguilleur l'a deja classee
#: EXECUTIVE). Repli sur les deux roles les plus transverses — meme principe
#: que le repli du Comite d'OpenExecutive (`cso`+`cfo`, « broadest range »),
#: adapte a ARENA : finance et risque couvrent le plus de terrain a eux deux.
LOCUTIONS_EVALUATION_GENERALE = (
    "evaluation executive", "évaluation exécutive", "executive assessment",
    "evaluation d'affaires", "évaluation d'affaires", "bilan", "situation actuelle",
    "situation globale", "rapport executif", "rapport exécutif",
    "brief executif", "brief exécutif", "resume executif", "résumé exécutif",
    "business assessment", "overall assessment", "current situation",
)
ROLES_PAR_DEFAUT = ("finance", "risque")


def selectionner(demande: str, maximum: int = MAXIMUM) -> List[RoleExecutif]:
    """Les roles que cette question appelle vraiment, du plus au moins
    convoque — souvent zero, rarement plus de trois en pratique."""
    texte = _sans_accents(demande)
    if not texte.strip():
        return []
    scores = [(role, _poids(role, texte)) for role in ROLES]
    retenus = [(role, poids) for role, poids in scores if poids > 0]
    if not retenus and any(
        _reconnait(_sans_accents(locution), texte) for locution in LOCUTIONS_EVALUATION_GENERALE
    ):
        return [par_identifiant(i) for i in ROLES_PAR_DEFAUT][:maximum]
    retenus.sort(key=lambda couple: (-couple[1], couple[0].identifiant))
    return [role for role, _ in retenus[:maximum]]


def par_identifiant(identifiant: str) -> RoleExecutif:
    for role in ROLES:
        if role.identifiant == identifiant:
            return role
    raise KeyError(f"role executif inconnu : {identifiant!r}")


def identifiants() -> List[str]:
    return [r.identifiant for r in ROLES]
