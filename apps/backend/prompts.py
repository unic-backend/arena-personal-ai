"""Instruction système d'ARENA.

Aucun fait daté n'est écrit en dur ici — voir la docstring de
`get_arena_system_prompt`. Le module est séparé pour que cette règle soit
vérifiable sur un fichier court plutôt que noyée dans le point d'entrée.
"""
from datetime import date

from apps.backend.runtime import memory

# Faits que le proprietaire peut enregistrer lui-meme en memoire longue. Rien
# n'est ecrit en dur : une valeur absente n'apparait tout simplement pas.
FAITS_DU_PROPRIETAIRE = [
    ("president", "President de la Republique du Senegal"),
    ("premier_ministre", "Premier ministre du Senegal"),
]


def date_du_jour() -> date:
    """Date lue sur la machine. Isolee pour que les tests puissent la fixer."""
    return date.today()


def get_arena_system_prompt() -> str:
    """Compose l'instruction systeme d'ARENA.

    Aucun fait date n'est ecrit en dur ici. La version precedente affirmait
    « Annee actuelle : 2026 » et nommait deux responsables politiques : trois
    valeurs figees dans le code, qui deviennent fausses sans que rien ne le
    signale. Ecrire une date dans un prompt ne donne pas de connaissance au
    modele — cela lui donne seulement de quoi paraitre a jour.

    Ce qui remplace : la date reellement lue sur la machine, une consigne
    explicite de ne pas repondre de memoire sur ce qui a pu changer, et les
    faits que le proprietaire a lui-meme enregistres — s'il l'a fait.
    """
    owner_name = memory.get_fact("owner") or "Saer"
    aujourd_hui = date_du_jour()

    lignes = [
        f"Tu es ARENA, l'IA autonome personnelle de {owner_name}.",
        f"Date du jour, lue sur la machine : {aujourd_hui.strftime('%d/%m/%Y')}.",
        "",
        "Connaitre la date ne te donne aucune connaissance des evenements recents.",
        "Si la reponse a pu changer depuis ton entrainement — actualite, derniere",
        "version d'un logiciel, prix, resultat, qui occupe un poste — ne reponds pas",
        "de memoire. Dis que tu n'en es pas sur : ARENA sait aller verifier sur le web.",
        "N'invente jamais une date, un chiffre ou un nom que tu n'as pas verifie.",
    ]

    enregistres = [
        f"- {libelle} : {valeur}"
        for cle, libelle in FAITS_DU_PROPRIETAIRE
        if (valeur := memory.get_fact(cle))
    ]
    if enregistres:
        lignes += [
            "",
            f"Faits enregistres par {owner_name} en memoire longue "
            "(ils peuvent avoir change depuis : verifie si la question porte dessus) :",
            *enregistres,
        ]

    lignes += ["", "Reponds en francais, de maniere exacte, claire et directe."]
    return "\n".join(lignes)
