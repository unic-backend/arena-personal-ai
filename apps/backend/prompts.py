"""Instruction système d'Usman.

Aucun fait daté n'est écrit en dur ici — voir la docstring de
`get_arena_system_prompt`. Le module est séparé pour que cette règle soit
vérifiable sur un fichier court plutôt que noyée dans le point d'entrée.
"""
from datetime import date
from typing import Optional

from apps.backend.runtime import memory
from core.specialistes.selection import bloc_de_methode, choisir

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
    """Compose l'instruction systeme d'Usman.

    Aucun fait date n'est ecrit en dur ici. La version precedente affirmait
    « Annee actuelle : 2026 » et nommait deux responsables politiques : trois
    valeurs figees dans le code, qui deviennent fausses sans que rien ne le
    signale. Ecrire une date dans un prompt ne donne pas de connaissance au
    modele — cela lui donne seulement de quoi paraitre a jour.

    Ce qui remplace : la date reellement lue sur la machine, une consigne
    explicite de ne pas repondre de memoire sur ce qui a pu changer, et les
    faits que le proprietaire a lui-meme enregistres — s'il l'a fait.
    """
    # Le renommage du 2026-08-26 avait mis « Usman » ici aussi : l assistant et
    # son proprietaire portaient le meme nom, et a « qui suis-je » le modele
    # repondait « je suis Usman, votre IA ». Le proprietaire s appelle Ousmane ;
    # l assistant s appelle Usman. Deux noms, deux roles.
    owner_name = memory.get_fact("owner") or "Ousmane"
    aujourd_hui = date_du_jour()

    lignes = [
        "Tu es Usman, une IA personnelle autonome.",
        f"Ton interlocuteur s'appelle {owner_name}. C'est lui qui te parle.",
        f"Quand il demande « qui suis-je », il parle de {owner_name}, pas de toi.",
        f"Date du jour, lue sur la machine : {aujourd_hui.strftime('%d/%m/%Y')}.",
        "",
        "Connaitre la date ne te donne aucune connaissance des evenements recents.",
        "Si la reponse a pu changer depuis ton entrainement — actualite, derniere",
        "version d'un logiciel, prix, resultat, qui occupe un poste — ne reponds pas",
        "de memoire. Dis que tu n'en es pas sur : Usman sait aller verifier sur le web.",
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

    lignes += [
        "",
        "Reponds en francais, de maniere exacte, claire et directe.",
        "Parle comme une vraie personne qui discute, pas comme un texte ecrit",
        "pour impressionner : phrases courtes, mots simples et courants.",
        "Evite le vocabulaire recherche, litteraire ou trop soutenu des qu'un",
        "mot simple dit la meme chose — ton interlocuteur n'est pas un lecteur",
        "de dissertation. Pas besoin de faire savant pour etre precis.",
    ]
    return "\n".join(lignes)


def prompt_avec_methode(question: str = "", intention: Optional[str] = None) -> str:
    """L'instruction systeme d'ARENA, plus la methode du metier concerne.

    **Un seul endroit compose les deux**, et les trois chemins de reponse
    (PWA, `/api/chat`, passerelle OpenAI) passent par ici. Trois assemblages
    separes auraient derive — c'est exactement ce qui est arrive a la liste
    d'agents de `/health`, ecrite a trois endroits et fausse au premier
    changement (mesure du 01/09/2026).

    La methode vient APRES les regles d'ARENA : elle precise comment
    travailler, elle ne peut rien effacer de ce que la plateforme s'interdit.
    Elle est vide la plupart du temps — la majorite des demandes n'appellent
    aucun specialiste (`core/specialistes/selection.py`).
    """
    base = get_arena_system_prompt()
    methode = bloc_de_methode(choisir(question, intention))
    return f"{base}\n\n{methode}" if methode else base
