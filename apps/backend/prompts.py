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
import logging
import re
import threading
import time
from datetime import date
from pathlib import Path
from typing import Callable, List, Optional

from apps.backend.runtime import memory
from core.specialistes.selection import bloc_de_methode, choisir

logger = logging.getLogger("usman.backend.prompts")

#: La consigne JARVIS du proprietaire (29/09/2026). Son identite, sa mission,
#: ses valeurs et sa discipline restent les siennes ; les sections qui
#: decrivent le fonctionnement suivent le code mesure (DEC-0163/0192).
FICHIER_JARVIS = Path(__file__).resolve().parents[2] / "config" / "jarvis.md"


def consigne_jarvis() -> str:
    """Le texte de `config/jarvis.md`, ou une ligne de repli s'il manque.

    Un fichier absent ne doit pas faire tomber le chat : JARVIS garde son nom
    et ses regles, il perd seulement la consigne detaillee — et le journal le dit.
    """
    try:
        texte = FICHIER_JARVIS.read_text(encoding="utf-8").strip()
    except OSError as erreur:
        logger.warning("Consigne JARVIS illisible (%s) : repli sur l'identite seule.", erreur)
        return "You are JARVIS, the executive orchestrator of ARENA Personal AI."
    # Les listes « 1. 2. 3. » de la consigne deviennent « (1) (2) (3) » : dans
    # le prompt, « 1. » a « 7. » designent les sept regles de DISCIPLINE, et
    # une seconde liste numerotee rendait « la regle 1 » ambigue — pour le
    # modele comme pour tests/test_discipline_du_prompt.py. Cette transformation
    # ne change pas le fichier source.
    return re.sub(r"^(\s*)(\d+)\.\s", r"\1(\2) ", texte, flags=re.MULTILINE)


#: Les agents d'un metier, joignables dans leur espace, jamais annonces ici.
MODULES_METIER = ("agents.plaquiste",)


def capacites_branchees() -> List[str]:
    """Les agents reellement inscrits dans le registre, une ligne chacun.

    La presence vient du registre vivant (DEC-0145), jamais d'une liste ecrite
    dans le prompt. Elle ne vaut pas disponibilite : l'etat mesure par
    `doctor.py` est compose juste a cote.
    """
    from apps.backend.runtime import collaborateurs

    lignes = []
    for fiche in collaborateurs.fiches():
        # Un agent metier n'entre pas dans l'instruction generale : seul son
        # espace connait l'entreprise (decision du 02/09/2026, en tete de ce
        # module). Reconnu par le nom de son module, sans l'importer.
        if str(fiche.metadata.get("module", "")).startswith(MODULES_METIER):
            continue
        quoi = ", ".join(fiche.capabilities) or fiche.description
        lignes.append(f"- {fiche.id} : {quoi}")
    return lignes


#: `doctor.py` a pris 0,53 a 0,86 s sur la machine d'audit du 30/09/2026.
#: Certaines sondes d'un moteur INSTALLE peuvent attendre bien davantage
#: (`DELAI_SONDE`, voire le demarrage d'un service). Une mesure par requete
#: ralentirait donc chaque phrase. Cinq minutes bornent cette dette a une
#: mesure pour plusieurs tours (0,08 s/tour amortie a un tour par minute sur
#: la machine d'audit), tout en rendant un service rallume visible sans
#: redemarrer ARENA. Une configuration changee par ARENA invalide sans attendre.
DUREE_CACHE_DIAGNOSTIC = 300.0
_CACHE_DIAGNOSTIC: Optional[tuple[float, List[str]]] = None
_VERROU_DIAGNOSTIC = threading.Lock()


def _lire_diagnostic():
    """Appelle la source canonique sans la recopier dans le backend."""
    from scripts.doctor import diagnostiquer

    return diagnostiquer()


def _etat_pour_le_modele(etat: str) -> str:
    """Forme stable et compacte : le nom des etats, jamais une capacite."""
    normalise = str(etat or "INCONNU").strip().upper().replace(" ", "_")
    if normalise == "OK":
        return "DISPONIBLE"
    if normalise == "NON_CONFIGURE":
        return "NOT_CONFIGURED"
    return normalise


def invalider_cache_diagnostic() -> None:
    """Force la prochaine composition a remesurer la machine.

    L'expiration temporelle couvre un service lance ou arrete. Cette porte
    explicite couvre une configuration changee par ARENA elle-meme (OAuth,
    tests, future interface de reglage) sans attendre l'expiration.
    """
    global _CACHE_DIAGNOSTIC
    with _VERROU_DIAGNOSTIC:
        _CACHE_DIAGNOSTIC = None


def etats_capacites_mesurees(
    horloge: Callable[[], float] = time.monotonic,
) -> List[str]:
    """Les mesures de `doctor.py`, mises en cache et rendues au modele.

    Une panne globale du diagnostic se dit `INCONNU` : elle ne transforme
    jamais une absence de mesure en disponibilite. Noms et etats viennent des
    `Verification` elles-memes ; aucune capacite n'est nommee ici a la main.
    """
    global _CACHE_DIAGNOSTIC
    maintenant = horloge()
    with _VERROU_DIAGNOSTIC:
        if _CACHE_DIAGNOSTIC is not None:
            mesuree_a, lignes = _CACHE_DIAGNOSTIC
            if maintenant - mesuree_a < DUREE_CACHE_DIAGNOSTIC:
                return list(lignes)
        try:
            rapport = _lire_diagnostic()
            # Nom + etat suffisent a la decision du modele. Les details et
            # remedes restent dans `python scripts/doctor.py` : les recopier
            # ici ajoutait plusieurs milliers de caracteres a chaque requete.
            lignes = [
                f"- {verification.nom} : {_etat_pour_le_modele(verification.etat)}"
                for verification in rapport.verifications
            ]
        except Exception as erreur:  # noqa: BLE001 — le prompt doit toujours partir
            logger.warning("Diagnostic des capacites illisible : %s", type(erreur).__name__)
            lignes = [
                "- Diagnostic des capacites : INCONNU — la mesure a echoue "
                f"({type(erreur).__name__})"
            ]
        _CACHE_DIAGNOSTIC = (maintenant, lignes)
        return list(lignes)


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
#: - Regle 4 : `ABSENT` et `UNKNOWN` sont deja distingues dans le code
#:   (`core/memory/semantique.py`, `ETAT_SERVEUR_ABSENT` / `ETAT_MODELE_ABSENT`) ;
#:   le modele, lui, melangeait les deux en parlant.
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
    """Compose l'instruction systeme de JARVIS.

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
    # l assistant s appelle JARVIS depuis le 29/09/2026 (decision du
    # proprietaire, DEC-0163). Deux noms, deux roles.
    owner_name = memory.get_fact("owner") or "Ousmane"
    aujourd_hui = date_du_jour()

    lignes = [
        "Tu es JARVIS, l'orchestrateur d'ARENA, une IA personnelle autonome.",
        f"Ton interlocuteur s'appelle {owner_name}. C'est lui qui te parle.",
        f"Quand il demande « qui suis-je », il parle de {owner_name}, pas de toi.",
        f"Date du jour, lue sur la machine : {aujourd_hui.strftime('%d/%m/%Y')}.",
        "",
        "Connaitre la date ne te donne aucune connaissance des evenements recents.",
        "Si la reponse a pu changer depuis ton entrainement — actualite, derniere",
        "version d'un logiciel, prix, resultat, qui occupe un poste — ne reponds pas",
        "de memoire. Dis que tu n'en es pas sur : JARVIS sait aller verifier sur le web.",
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

    # La consigne du proprietaire, puis les DEUX mesures qui font foi, puis les
    # regles : la discipline vient APRES, elle prime sur l'envie d'etre utile.
    # Le registre dit ce qui existe ; doctor.py dit ce qui fonctionne. Confondre
    # les deux faisait annoncer « email » quand Gmail etait NON_CONFIGURE.
    lignes += ["", consigne_jarvis()]
    branchees = capacites_branchees()
    mesurees = etats_capacites_mesurees()
    lignes += [
        "",
        "CAPACITES DE CETTE INSTALLATION — COMPOSEES A CHAQUE APPEL, JAMAIS",
        "RECOPIEES DANS LA CONSIGNE.",
        "",
        "AGENTS ENREGISTRES (presence dans le registre, pas preuve que leurs",
        "outils repondent) :",
        *(branchees or ["- aucun agent enregistre"]),
        "",
        "ETAT MESURE DE LA MACHINE (source : scripts/doctor.py ; une panne reste",
        "visible avec son etat, elle ne disparait pas de la liste) :",
        *mesurees,
        "",
        "Une capacite est utilisable seulement si son agent existe ET si les",
        "mesures dont elle depend sont DISPONIBLE. NOT_CONFIGURED, ABSENT,",
        "EN_PANNE et INCONNU ne sont jamais des disponibilites.",
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
        "",
        # Mesure du 15/09/2026 : « Resous l'equation x2 - 5x + 6 = 0 » est
        # revenue sur le telephone du proprietaire avec `\[ x^{2}-5x+6=0 \]`,
        # `\Delta = b^{2}-4ac` et `\frac{-b\pm\sqrt{\Delta}}{2a}` affiches
        # TELS QUELS. L'interface ne rend pas LaTeX — `apps/pwa` n'embarque ni
        # KaTeX ni MathJax — donc une reponse de maths y devient illisible.
        # Ecrire la consigne ici plutot que d'ajouter un moteur de rendu au
        # paquet : la PWA est un fichier unique embarque sur un telephone, et
        # les maths d'un artisan se lisent tres bien en Unicode.
        "N'ecris JAMAIS de LaTeX : ni \\[ \\], ni \\( \\), ni \\frac, ni \\sqrt,",
        "ni \\Delta. L'interface ne sait pas les afficher et les montre tels",
        "quels. Ecris les mathematiques en texte simple : x² - 5x + 6 = 0,",
        "Δ = b² - 4ac = 1, √Δ = 1, x = (5 ± 1) / 2, donc x = 2 ou x = 3.",
        "Les exposants, racines et lettres grecques existent en Unicode :",
        "utilise-les.",
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
