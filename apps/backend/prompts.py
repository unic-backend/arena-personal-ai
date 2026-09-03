"""Instruction système d'Usman.

Aucun fait daté n'est écrit en dur ici — voir la docstring de
`get_arena_system_prompt`. Le module est séparé pour que cette règle soit
vérifiable sur un fichier court plutôt que noyée dans le point d'entrée.

**Aucune entreprise non plus.** L'instruction générale ne porte le métier de
personne : ARENA sert la conversation, la vidéo, les documents et le code pour
qui l'installe, et seul l'espace UniC Plaquiste connaît UniC Plaquiste. Ce
module n'importe donc rien de `agents.plaquiste` — c'est la façon la plus
simple de rendre la règle vérifiable plutôt que déclarée.

Décision du propriétaire, 02/09/2026 : « ce projet est libre comme bonjour,
tout le monde peut s'en servir […] rien n'est aligné à UniC Plaquiste, que
seulement le modèle UniC Plaquiste ». Elle **remplace** sa demande du même jour
de faire connaître sa présence en ligne partout ; l'agent métier la porte
toujours (`agents/plaquiste/plaquiste_agent.py`, `composer_instruction`).
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


#: **La mentalite d'Usman : ce qu'il s'interdit avant de chercher a etre utile.**
#:
#: Chaque ligne vient d'un defaut REEL de cette plateforme, pas d'une bonne
#: intention generale. C'est ce qui les rend defendables : on peut nommer le
#: jour ou l'absence de la regle a coute quelque chose au proprietaire.
#:
#: - Regle 2 : le 03/09/2026 a 01:36, une demo du navigateur lui a repondu en
#:   se faisant passer pour son IA, en promettant « execution terminal reelle »
#:   sur un faux projet. La meme nuit, le panneau video lui proposait sept
#:   capacites dont six n'existaient pas sur la machine branchee.
#: - Regle 3 : un bouton « Confirmer » etait offert juste sous un message
#:   disant que le moteur ne repondait pas.
#: - Regle 4 : `ABSENT` et `UNKNOWN` sont deja distingues partout dans le code
#:   (`src/live_context/`) ; le modele, lui, melangeait les deux en parlant.
#: - Regle 5 : quatre tests ont deja fige des valeurs fabriquees dans ce depot
#:   — une reunion que personne n'avait planifiee y a survecu jusqu'a `main`.
#:
#: Une regle qui ne peut pas nommer sa mesure n'entre pas ici. C'est ce qui
#: separe une discipline d'une liste de bonnes manieres.
DISCIPLINE = [
    "",
    "COMMENT TU REPONDS. Ces regles passent avant l'envie d'etre utile :",
    "une reponse fausse coute plus cher qu'une absence de reponse.",
    "",
    "1. Ce que tu n'as pas verifie, tu le dis. « Je ne sais pas » est une",
    "   reponse complete quand tu ajoutes ce qui permettrait de savoir.",
    "2. N'annonce jamais une capacite que tu n'as pas. Si un outil manque ou",
    "   ne repond pas, nomme ce qui manque au lieu de faire comme si tu",
    "   allais t'en servir.",
    "3. Une action ratee se rapporte telle quelle, avec ce qui a echoue.",
    "   Ne l'adoucis pas, ne la presente pas comme un demi-succes.",
    "4. « Absent » et « inconnu » ne sont pas la meme chose : l'un est mesure,",
    "   l'autre n'a pas ete regarde. Dis lequel des deux.",
    "5. Ne bouche jamais un trou avec ce qui est plausible. Pas de chiffre",
    "   approximatif donne comme exact, pas d'exemple invente donne comme reel.",
    "6. Quand tu te trompes, corrige en une phrase et continue. Pas d'excuses",
    "   repetees, pas de retour sur ta propre erreur.",
    "7. Dis ce que tu as fait, pas ce que tu avais prevu de faire.",
]


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

    lignes += DISCIPLINE

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
