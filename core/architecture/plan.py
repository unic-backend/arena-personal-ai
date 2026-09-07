"""D'une phrase à des opérations d'architecture — sans appeler aucun modèle.

**Pourquoi sans modèle.** ARENA doit répondre quand Ollama est éteint : c'est
la règle qui a fait du repli par mots-clés le seul classificateur réel du
dépôt. Un plan produit ici est donc *vérifiable* — la même phrase donne
toujours les mêmes opérations, et un test peut l'affirmer.

**Ce que ça n'empêche pas.** Un modèle qui saurait faire mieux produit
exactement la même chose : une liste d'`Operation` du vocabulaire d'ARENA.
La capacité ne sait pas d'où vient le plan, et c'est ce qui la garde
agnostique — le planificateur est *une* source, jamais la seule.

**Ce qui n'est pas fait, et pourquoi.** Pascal expose `create_house_from_brief`,
qui accepte une phrase entière. Mesuré le 07/09/2026 : sur
« maison 20x15 avec 3 chambres », il rend un projet bâti sur le gabarit
`empty-studio` — il **choisit un gabarit** au lieu d'honorer la demande. Le
brancher aurait donné une maison plausible et fausse. ARENA compose donc
elle-même, à partir de primitives dont chaque effet est mesurable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

#: « 20m x 15m », « 20 x 15 », « 20m sur 15m ». La virgule décimale française
#: est acceptée : il écrit « 4,5 m », jamais « 4.5 m ».
DIMENSIONS = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:m|metres?|mètres?)?\s*(?:x|\*|par|sur)\s*"
    r"(\d+(?:[.,]\d+)?)\s*(?:m|metres?|mètres?)?", re.IGNORECASE)

#: « 3 chambres », « trois chambres ».
CHIFFRES = {"une": 1, "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
            "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10}

#: Les pièces qu'ARENA sait nommer. Chacune est un mot qu'il emploie
#: réellement — pas un vocabulaire d'architecte.
PIECES = {
    "chambre": "Chambre", "salon": "Salon", "cuisine": "Cuisine",
    "salle de bain": "Salle de bain", "salle d'eau": "Salle d'eau",
    "bureau": "Bureau", "terrasse": "Terrasse", "garage": "Garage",
    "couloir": "Couloir", "entree": "Entrée", "entrée": "Entrée",
    "wc": "WC", "buanderie": "Buanderie", "sejour": "Séjour", "séjour": "Séjour",
}

#: Hauteur sous plafond par défaut, en mètres. Valeur courante au Sénégal pour
#: du logement ; elle est **explicite** dans le plan rendu, jamais cachée.
HAUTEUR_DEFAUT = 2.5


@dataclass
class Operation:
    """Une opération du vocabulaire d'ARENA, prête à être exécutée."""

    nom: str
    parametres: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """Ce qu'ARENA a compris, et ce qu'elle n'a pas compris.

    `non_compris` n'est pas décoratif : c'est ce qui empêche un plan
    incomplet de se présenter comme complet. Un plan qui tait ce qu'il a
    ignoré fabrique la confiance qu'il ne mérite pas.
    """

    operations: List[Operation] = field(default_factory=list)
    compris: List[str] = field(default_factory=list)
    non_compris: List[str] = field(default_factory=list)


def _nombre(texte: str, mot: str) -> int:
    """Combien de « mot » la phrase demande. 0 si elle n'en parle pas."""
    for motif in (rf"(\d+)\s+{mot}", rf"([a-zéè]+)\s+{mot}"):
        trouve = re.search(motif, texte, re.IGNORECASE)
        if not trouve:
            continue
        brut = trouve.group(1).lower()
        if brut.isdigit():
            return int(brut)
        if brut in CHIFFRES:
            return CHIFFRES[brut]
    return 1 if re.search(rf"\b{mot}", texte, re.IGNORECASE) else 0


def _motif_pluriel(mot: str) -> str:
    """« salle de bain » -> un motif qui attrape aussi « salles de bain ».

    **Mesure du 07/09/2026** : une première version ajoutait un `s?` à la fin
    seulement. Sur « 2 salles de bain », elle ne trouvait rien — le pluriel
    français porte sur le premier mot, pas le dernier — et la pièce demandée
    disparaissait du plan **en silence**. Un plan qui perd une pièce sans le
    dire est pire qu'un plan qui refuse.
    """
    return r"\s+".join(re.escape(m) + "s?" for m in mot.split())


def _pieces_demandees(texte: str) -> List[str]:
    """Les pièces nommées dans la phrase, avec leurs répétitions."""
    demandees: List[str] = []
    for mot, etiquette in PIECES.items():
        combien = _nombre(texte, _motif_pluriel(mot))
        if combien <= 0:
            continue
        if combien == 1:
            demandees.append(etiquette)
        else:
            demandees.extend(f"{etiquette} {i}" for i in range(1, combien + 1))
    return demandees


def _grille(largeur: float, profondeur: float, combien: int) -> List[List[List[float]]]:
    """Découpe l'emprise en `combien` polygones, en bandes régulières.

    **Ce que ce découpage n'est pas** : un plan d'architecte. C'est une
    répartition régulière, honnête et vérifiable — chaque pièce reçoit une
    part égale de l'emprise. Le propriétaire déplace ensuite les cloisons
    dans l'éditeur ; ARENA ne prétend pas concevoir à sa place.
    """
    if combien <= 0:
        return []
    colonnes = min(combien, 3)
    lignes = (combien + colonnes - 1) // colonnes
    pas_x, pas_y = largeur / colonnes, profondeur / lignes
    polygones = []
    for index in range(combien):
        cx, cy = index % colonnes, index // colonnes
        x0, y0 = round(cx * pas_x, 3), round(cy * pas_y, 3)
        x1, y1 = round(x0 + pas_x, 3), round(y0 + pas_y, 3)
        polygones.append([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    return polygones


def planifier(phrase: str, nom_projet: str = "") -> Plan:
    """La phrase du propriétaire -> les opérations qu'ARENA va exécuter.

    Le plan est rendu **sans rien exécuter** : c'est ce qui permet de le
    montrer avant confirmation, et de le tester sans moteur.
    """
    texte = (phrase or "").strip()
    plan = Plan()
    if not texte:
        plan.non_compris.append("aucune demande")
        return plan

    dimensions = DIMENSIONS.search(texte)
    if not dimensions:
        plan.non_compris.append(
            "aucune dimension trouvee : precise par exemple « 20m x 15m »")
        return plan

    largeur = float(dimensions.group(1).replace(",", "."))
    profondeur = float(dimensions.group(2).replace(",", "."))
    plan.compris.append(f"emprise {largeur} m x {profondeur} m")

    plan.operations.append(Operation("creer_projet", {
        "titre": nom_projet or f"Batiment {largeur:g}x{profondeur:g}"}))
    plan.operations.append(Operation("lister_niveaux", {}))
    plan.operations.append(Operation("creer_coque", {
        "emprise": [[0, 0], [largeur, 0], [largeur, profondeur], [0, profondeur]],
        "hauteur_murs": HAUTEUR_DEFAUT}))
    plan.compris.append(f"hauteur sous plafond {HAUTEUR_DEFAUT} m (valeur par defaut)")

    pieces = _pieces_demandees(texte)
    if pieces:
        for etiquette, polygone in zip(pieces, _grille(largeur, profondeur, len(pieces)), strict=True):
            plan.operations.append(Operation("creer_piece", {
                "titre": etiquette, "polygone": polygone}))
        plan.compris.append(f"{len(pieces)} piece(s) : {', '.join(pieces)}")
        plan.compris.append(
            "pieces reparties en bandes regulieres — a deplacer dans l'editeur")
    else:
        plan.non_compris.append(
            "aucune piece nommee : la coque est creee, rien n'est cloisonne")

    return plan


def resumer(plan: Plan) -> str:
    """Le plan en français, tel qu'on le lui montre avant de l'exécuter."""
    lignes = [f"{len(plan.operations)} operation(s) prevue(s)."]
    if plan.compris:
        lignes.append("Compris : " + " ; ".join(plan.compris) + ".")
    if plan.non_compris:
        lignes.append("Non compris : " + " ; ".join(plan.non_compris) + ".")
    return "\n".join(lignes)


def sequence(plan: Plan) -> List[Tuple[str, Dict[str, Any]]]:
    """Le plan sous la forme que la couche d'exécution consomme."""
    return [(o.nom, dict(o.parametres)) for o in plan.operations]


def executer(registre: Any, phrase: str, session: str = "defaut",
             nom_projet: str = "") -> Dict[str, Any]:
    """La phrase -> le plan -> le connecteur. **Sans agent, sans modèle.**

    C'est le chemin complet demandé par la mission :

    ```
    phrase -> plan (ici) -> connecteur architecture_3d
           -> permission -> confirmation -> capacite -> backend -> moteur
    ```

    **Une seule confirmation pour tout le plan**, et le message de
    confirmation montre le plan en entier — y compris ce qu'ARENA n'a pas
    compris. Onze confirmations pour une phrase seraient inutilisables ; une
    confirmation muette serait pire. Le compromis est explicite, pas subi.

    Le plan est rendu ici **avant** l'appel, pour que la réponse dise ce qui
    a été compris même quand l'action part en attente de confirmation.
    """
    plan = planifier(phrase, nom_projet=nom_projet)
    if not plan.operations:
        return {"status": "warning", "agent": "architecture_3d",
                "response": ("Je n'ai pas compris ce qu'il faut construire.\n"
                             + resumer(plan)),
                "plan": resumer(plan)}

    resultat = registre.executer("architecture_3d", "batir_plan",
                                 session=session, phrase=phrase, titre=nom_projet)
    statut = resultat.statut.value
    etat = {"SUCCESS": "success", "NEEDS_CONFIRMATION": "pending"}.get(statut, "error")
    return {
        "status": etat, "agent": "architecture_3d",
        "response": resultat.message,
        "plan": resumer(plan), "session": session,
        "operations": resultat.detail.get("operations", []),
    }
