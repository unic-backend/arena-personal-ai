"""La chronologie des actions, telle qu'un humain la lit.

La specification en donne la forme exacte : heure, action, service, cible,
resultat, verification. Ce module ne fait que rendre ce que le journal a
enregistre — il ne calcule aucun etat et n'en devine aucun.

Un point de vocabulaire qui n'est pas cosmetique : la colonne « resultat »
affiche le statut tel qu'il a ete ecrit (`SUCCESS`, `NOT_CONFIGURED`, `DENIED`…)
et **jamais une coche ou une croix**. Deux symboles pour sept etats forcerait a
ranger « non configure » du cote de l'echec ou du cote de la reussite, et les
deux seraient faux.
"""
from typing import Any, Dict, List

from core.actions.journal import ActionEnregistree, EtatVerification

# Ce qui s'affiche a la place d'une preuve absente. Vide serait ambigu : on ne
# saurait pas si la preuve manque ou si l'action n'en attendait pas.
SANS_PREUVE = "—"

COLONNES = ("heure", "action", "service", "cible", "resultat", "verification", "preuve")


def _heure(horodatage: str) -> str:
    """« 2026-08-27T08:32:00+00:00 » devient « 08:32 ». Rend le brut si illisible."""
    try:
        return horodatage.split("T", 1)[1][:5]
    except (IndexError, AttributeError):
        return str(horodatage)


def en_lignes(actions: List[ActionEnregistree]) -> List[Dict[str, str]]:
    """Une ligne par action, prete a etre affichee ou transportee en JSON."""
    return [
        {
            "heure": _heure(action.horodatage),
            "horodatage": action.horodatage,
            "action": action.action,
            "service": action.outil,
            "cible": action.cible,
            "resultat": action.resultat,
            "verification": action.verification.value,
            "preuve": action.preuve or SANS_PREUVE,
            "erreurs": action.erreurs or "",
            "id": action.identifiant,
            # Le fil de la demande (13/09/2026). Il rejoint `horodatage`,
            # `erreurs` et `id` : rendu en JSON, **hors** de `COLONNES**, donc
            # absent du tableau texte. Un identifiant de 32 caracteres par
            # ligne rendrait la chronologie illisible pour l'humain qu'elle
            # sert, alors qu'un client a besoin de lui pour recoller la trace.
            # `None` pour une action d'avant cette date : elle n'a jamais eu de
            # fil, et lui en inventer un serait une trace fabriquee.
            "requete": action.requete,
        }
        for action in actions
    ]


def formater(actions: List[ActionEnregistree]) -> str:
    """Rend la chronologie en texte aligne, la plus recente en haut.

    Un journal vide le dit. C'est le cas qui compte le plus : pendant des mois,
    la table d'audit d'ARENA etait vide et rien ne le signalait.
    """
    if not actions:
        return "Aucune action enregistree."

    lignes = en_lignes(actions)
    largeurs = {
        colonne: max(len(colonne), *(len(ligne[colonne]) for ligne in lignes))
        for colonne in COLONNES
    }

    def rendre(valeurs: Dict[str, str]) -> str:
        return "  ".join(valeurs[colonne].ljust(largeurs[colonne]) for colonne in COLONNES)

    entete = rendre({colonne: colonne.upper() for colonne in COLONNES})
    return "\n".join([entete, "-" * len(entete)] + [rendre(ligne) for ligne in lignes])


def resume(actions: List[ActionEnregistree]) -> Dict[str, int]:
    """Compte les actions par resultat, et combien ont un effet verifie.

    `avec_effet_verifie` n'est pas « les succes » : c'est le nombre d'actions
    dont on peut prouver qu'elles ont change quelque chose dehors.
    """
    compte: Dict[str, int] = {"total": len(actions), "avec_effet_verifie": 0}
    for action in actions:
        compte[action.resultat] = compte.get(action.resultat, 0) + 1
        if action.verification is EtatVerification.VERIFIEE:
            compte["avec_effet_verifie"] += 1
    return compte


def to_dict(actions: List[ActionEnregistree]) -> Dict[str, Any]:
    """La chronologie complete, telle que l'API la rend."""
    return {"resume": resume(actions), "actions": en_lignes(actions)}
