"""Retrouver le bon souvenir, sans charger toute la memoire dans le prompt.

La specification pose les deux contraintes ensemble, et elles tirent en sens
inverse : « le systeme doit pouvoir retrouver quelque chose d'il y a des mois »
et « la memoire doit passer a l'echelle sans ralentir les reponses ». Tout
charger repond a la premiere et trahit la seconde.

Ce module choisit. Quatre signaux, un budget dur, et une explication.

**Quatre regles :**

1. **Le budget est une limite, pas un objectif.** Ce qui est rendu tient dans
   `budget_caracteres`, toujours. Un souvenir de plus qui ferait deborder n'est
   pas tronque : il n'est pas pris. Un prompt qui grossit avec la memoire est un
   prompt qui finit par ne plus tenir.

2. **La recence seule ne fait pas remonter un souvenir.** Sans lien avec la
   question — mot commun, projet nomme, ou fenetre de temps demandee — un
   souvenir reste ou il est, si frais soit-il. Autrement, ARENA repondrait a
   chaque question avec ce qu'il vient d'apprendre.

3. **Chaque resultat dit pourquoi il est la.** Un classement qu'on ne peut pas
   expliquer est un classement qu'on ne peut pas corriger.

4. **Une supposition reste marquee comme telle jusque dans le prompt.** Le
   modele ne doit pas lire une deduction d'ARENA comme un fait du proprietaire.
"""
import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from core.memory.personnelle import (
    MemoirePersonnelle,
    Souvenir,
    TypeSouvenir,
    est_un_echec_de_lecture,
)
from core.observabilite.fil import compter_souvenirs_lus

logger = logging.getLogger("usman.memoire.recuperation")

# Poids des quatre signaux. Ils somment a 1 et sont ecrits ici plutot que
# disperses : un classement dont on ne voit pas la formule ne se regle pas.
POIDS = {
    "correspondance": 0.50,  # mots communs entre la question et le souvenir
    "importance": 0.20,      # ce que l'appelant a declare en le retenant
    "recence": 0.15,         # decroissance douce avec l'age
    "temporel": 0.15,        # le souvenir tombe dans la fenetre demandee
}

# Un souvenir met environ trois mois a perdre la moitie de son score de recence.
# Assez lent pour qu'un chantier d'il y a quatre mois reste atteignable.
DEMI_VIE_JOURS = 90.0

# En dessous, le souvenir n'a rien a voir avec la question.
SEUIL = 0.10

# Budget par defaut : de quoi tenir dans un prompt sans l'ecraser.
BUDGET_PAR_DEFAUT = 2000

# Mots trop courants pour dire quoi que ce soit d'une question.
MOTS_VIDES = frozenset("""
a ai as au aux avec car ce ces dans de des du elle en es est et eu eux il je la
le les leur lui ma mais me meme mes moi mon ne ni nos notre nous on or ou par
pas pour qu que qui sa se ses si son sont sur ta te tes toi ton tu un une va vos
votre vous vu y etait etaient
c d j l m n s t quoi dont comme fait faire dis dit
""".split())

# Longueur minimale d'un mot retenu. **Deux, pas trois** : « m2 » est dans
# presque toutes les phrases du proprietaire, et le couper de la recherche
# rendait « combien de m2 » aveugle a ses propres devis. Les mots de deux
# lettres sans interet sont ecartes par la liste ci-dessus, pas par leur taille.
LONGUEUR_MINIMALE = 2


def normaliser(texte: str) -> str:
    """Minuscules, sans accents. « Médina » et « medina » sont le meme mot."""
    sans_accent = unicodedata.normalize("NFD", texte or "")
    sans_accent = "".join(c for c in sans_accent if unicodedata.category(c) != "Mn")
    return sans_accent.lower()


def mots_utiles(texte: str) -> set:
    """Les mots qui portent du sens, normalises."""
    return {
        mot for mot in re.findall(r"[a-z0-9]+", normaliser(texte))
        if len(mot) >= LONGUEUR_MINIMALE and mot not in MOTS_VIDES
    }


# --- Le temps, tel qu'on en parle ---------------------------------------------

UNITES_JOURS = {
    "jour": 1, "jours": 1,
    "semaine": 7, "semaines": 7,
    "mois": 30,
    "an": 365, "ans": 365, "annee": 365, "annees": 365,
}

# « il y a quatre mois » : c'est la formulation exacte de la specification.
NOMBRES = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
}

MOTIF_IL_Y_A = re.compile(
    r"il y a\s+(\d+|" + "|".join(NOMBRES) + r")\s+(" + "|".join(UNITES_JOURS) + r")\b"
)

RACCOURCIS = {
    "hier": (0, 2),
    "avant-hier": (1, 3),
    "la semaine derniere": (5, 14),
    "le mois dernier": (25, 40),
    "l annee derniere": (330, 400),
}

#: Largeur de la fenetre autour d'une date evoquee, en proportion de son age.
#: « il y a quatre mois » ne veut pas dire « le 120e jour » : c'est une saison.
LARGEUR_FENETRE = 0.35


def fenetre_evoquee(
    question: str, maintenant: Optional[datetime] = None
) -> Optional[Tuple[datetime, datetime]]:
    """La periode dont parle la question, ou None si elle n'en evoque aucune.

    « Continue le projet d'il y a quatre mois » rend une fenetre large autour de
    la date, pas un jour precis : personne ne compte les jours en parlant.
    """
    maintenant = maintenant or datetime.now(timezone.utc)
    texte = normaliser(question)

    for expression, (min_jours, max_jours) in RACCOURCIS.items():
        if expression in texte:
            return (maintenant - timedelta(days=max_jours),
                    maintenant - timedelta(days=min_jours))

    trouve = MOTIF_IL_Y_A.search(texte)
    if not trouve:
        return None

    quantite_brute, unite = trouve.group(1), trouve.group(2)
    quantite = int(quantite_brute) if quantite_brute.isdigit() else NOMBRES[quantite_brute]
    jours = quantite * UNITES_JOURS[unite]
    marge = max(3.0, jours * LARGEUR_FENETRE)

    return (maintenant - timedelta(days=jours + marge),
            maintenant - timedelta(days=max(0.0, jours - marge)))


# --- Le classement -------------------------------------------------------------

@dataclass(frozen=True)
class Resultat:
    """Un souvenir retenu, son score, et le detail qui l'explique."""

    souvenir: Souvenir
    score: float
    signaux: Dict[str, float] = field(default_factory=dict)

    def pourquoi(self) -> str:
        """La raison du classement, en une ligne lisible."""
        parts = [f"{nom} {valeur:.2f}" for nom, valeur in self.signaux.items() if valeur > 0]
        return f"score {self.score:.2f} ({', '.join(parts) or 'aucun signal'})"


def _recence(souvenir: Souvenir, maintenant: datetime) -> float:
    """Decroissance exponentielle avec l'age. Une date illisible ne vaut rien."""
    try:
        age = (maintenant - datetime.fromisoformat(souvenir.cree_le)).total_seconds()
    except (ValueError, TypeError):
        return 0.0
    jours = max(0.0, age / 86400.0)
    return math.pow(0.5, jours / DEMI_VIE_JOURS)


def _dans_la_fenetre(souvenir: Souvenir, fenetre: Optional[Tuple[datetime, datetime]]) -> bool:
    if fenetre is None:
        return False
    try:
        date = datetime.fromisoformat(souvenir.cree_le)
    except (ValueError, TypeError):
        return False
    return fenetre[0] <= date <= fenetre[1]


def noter(
    souvenir: Souvenir,
    mots_question: set,
    fenetre: Optional[Tuple[datetime, datetime]],
    maintenant: datetime,
) -> Resultat:
    """Note un souvenir sur les quatre signaux, et garde le detail."""
    mots_souvenir = mots_utiles(souvenir.contenu) | mots_utiles(souvenir.projet or "")
    communs = mots_question & mots_souvenir
    correspondance = len(communs) / len(mots_question) if mots_question else 0.0

    signaux = {
        "correspondance": correspondance,
        "importance": souvenir.importance,
        "recence": _recence(souvenir, maintenant),
        "temporel": 1.0 if _dans_la_fenetre(souvenir, fenetre) else 0.0,
    }
    score = sum(POIDS[nom] * valeur for nom, valeur in signaux.items())
    return Resultat(souvenir=souvenir, score=score, signaux=signaux)


#: Combien de souvenirs SENSIBLES sont dechiffres au maximum pour une question.
#: Separe de `limite_lecture` volontairement : cette population est rare (le
#: proprietaire marque `sensible=True` un code, un acces, un montant — pas une
#: note de chantier), et la borne peut donc etre large sans rien couter. Mesure
#: du 12/09/2026 : 2000 souvenirs sensibles dechiffres et filtres coutent
#: **58,3 ms** quand ils partagent un sel, parce que la cle est alors derivee
#: UNE fois (`core/memory/chiffrement.py`, DEC-0096) et que le reste est de
#: l'AES-GCM. Le cout ne suit PAS le nombre de lignes mais le nombre de sels
#: DISTINCTS a derive — c'est pour cela que le sel d'ecriture est conserve
#: entre deux processus (`Coffre(chemin_sel=...)`, DEC-0097) : sans lui, 500
#: souvenirs ecrits au fil de 100 sessions coutaient **26,7 s** a la premiere
#: question, contre 285 ms avec.
LIMITE_SENSIBLES = 2000


def sensibles_correspondants(
    memoire: MemoirePersonnelle,
    mots_question: set,
    projet: Optional[str] = None,
    type: Optional[TypeSouvenir] = None,
    limite: int = LIMITE_SENSIBLES,
) -> List[Souvenir]:
    """Les souvenirs SENSIBLES dont le contenu partage un mot avec la question.

    La TROISIEME fenetre de `candidats_bornes`, et la seule qui ne peut pas
    filtrer en SQL : un souvenir sensible est chiffre sur le disque
    (DEC-0090), donc `LIKE '%portail%'` ne le trouvera jamais. Il faut
    dechiffrer avant de filtrer — ce qui etait inabordable jusqu'au 12/09/2026
    (275 ms de PBKDF2 par souvenir) et coute desormais une derivation pour
    toute la fenetre (DEC-0096).

    Ce que ca repare, mesure avant d'ecrire une ligne (DEC-0097) : « Le code du
    portail du chantier Fast Group est 4821. », marque sensible, vieux de 400
    jours et peu important, ne ressortait ni sur « quel est le code du portail
    Fast Group ? », ni sur « code portail chantier », ni sur « 4821 ». Le
    souvenir existait ; aucune question ne pouvait l'atteindre.

    Deux precautions, chacune gardee par un test :

    - **un message d'echec n'est pas un contenu.** Quand le coffre manque ou
      refuse, `souvenirs()` rend un etat lisible (`SANS_COFFRE`,
      `DECHIFFREMENT_REFUSE`) a la place du clair. Le filtrer sur des mots
      ferait remonter tout souvenir illisible des que la question contient
      « coffre » ou « sensible » : `est_un_echec_de_lecture` les ecarte.
    - **sans coffre, on ne fouille rien** : rien n'est lisible, la fenetre est
      vide, et ARENA le dit par l'absence de resultat, jamais par une
      supposition.

    Comme les deux autres fenetres, celle-ci est BORNEE (`limite`) : au-dela,
    ce sont les souvenirs sensibles les moins importants et les plus anciens
    qui restent hors de portee — la meme limite que partout ailleurs, ecrite
    plutot que decouverte.

    Le filtrage passe par `mots_utiles`, donc par `normaliser` : un mot
    accentue du contenu original est compare sans accent, ce que le `LIKE` SQL
    de la seconde fenetre ne sait pas faire.
    """
    if not mots_question or memoire.coffre is None:
        return []

    retenus: List[Souvenir] = []
    for souvenir in memoire.souvenirs(
        projet=projet, type=type, limite=limite, sensible=True
    ):
        if est_un_echec_de_lecture(souvenir.contenu):
            continue
        if mots_utiles(souvenir.contenu) & mots_question:
            retenus.append(souvenir)
    return retenus


def candidats_bornes(
    memoire: MemoirePersonnelle,
    mots_question: set,
    projet: Optional[str],
    type: Optional[TypeSouvenir],
    limite_lecture: int,
) -> List[Souvenir]:
    """Les souvenirs a noter — trois chemins bornes, jamais un chargement complet.

    `souvenirs()` rend la fenetre importance/recence habituelle (au plus
    `limite_lecture`). Sans rien d'autre, un souvenir pertinent mais ancien et
    peu important — hors de cette fenetre — n'etait jamais meme EXAMINE par
    `noter()`, quel que soit son score potentiel (mission ARENA x AUDIT,
    corrige le 12/09/2026 : « plus de 500 souvenirs, celui qui compte est hors
    de la fenetre »).

    `souvenirs_correspondant_a_des_mots()` ajoute une SECONDE fenetre, elle
    aussi bornee a `limite_lecture`, filtree en SQL sur les mots de la
    question — jamais un troisieme chargement complet, jamais un embedding
    supplementaire (ceux-la restent decides par l'appelant semantique). Les
    deux fenetres sont fusionnees, dedupliquees par identifiant ; `noter()`
    scoire ensuite l'union exactement comme avant.

    `sensibles_correspondants()` ajoute une TROISIEME fenetre, pour la seule
    population que le `LIKE` SQL ne peut pas fouiller : les souvenirs chiffres
    au repos. Elle est bornee comme les deux autres, et vide quand aucun
    coffre n'est configure. Sans elle, un code de portail marque sensible
    n'etait atteignable par AUCUN mot-cle une fois sorti de la premiere
    fenetre (mesure DEC-0097).
    """
    candidats = memoire.souvenirs(projet=projet, type=type, limite=limite_lecture)
    if not mots_question:
        return candidats

    vus = {souvenir.identifiant for souvenir in candidats}
    complement = memoire.souvenirs_correspondant_a_des_mots(
        mots_question, projet=projet, type=type, limite=limite_lecture)
    candidats = candidats + [s for s in complement if s.identifiant not in vus]

    # TROISIEME fenetre : les sensibles, que le `LIKE` SQL ci-dessus ne peut
    # pas fouiller puisque leur contenu est chiffre sur le disque.
    vus = {souvenir.identifiant for souvenir in candidats}
    chiffres = sensibles_correspondants(
        memoire, mots_question, projet=projet, type=type)
    candidats = candidats + [s for s in chiffres if s.identifiant not in vus]
    return candidats


def recuperer(
    memoire: MemoirePersonnelle,
    question: str,
    budget_caracteres: int = BUDGET_PAR_DEFAUT,
    projet: Optional[str] = None,
    type: Optional[TypeSouvenir] = None,
    limite_lecture: int = 500,
    maintenant: Optional[datetime] = None,
) -> List[Resultat]:
    """Rend les souvenirs pertinents, tries, dans la limite du budget.

    Args:
        memoire: la memoire a interroger.
        question: la demande, en clair.
        budget_caracteres: taille maximale du texte rendu. **Limite dure.**
        projet: restreint a un projet, quand l'appelant le connait deja.
        type: restreint a un type de souvenir.
        limite_lecture: combien de souvenirs sont examines au maximum.
        maintenant: pour que les tests fixent l'heure.

    Returns:
        Les resultats, du plus pertinent au moins. Une liste vide quand rien ne
        correspond — jamais le souvenir le moins mauvais.
    """
    maintenant = maintenant or datetime.now(timezone.utc)
    mots_question = mots_utiles(question)
    fenetre = fenetre_evoquee(question, maintenant)

    # Les perimes sont deja ecartes par `souvenirs()` : un contexte temporaire
    # perime ne doit pas revenir par la porte de la recuperation.
    candidats = candidats_bornes(memoire, mots_question, projet, type, limite_lecture)

    notes = [noter(souvenir, mots_question, fenetre, maintenant) for souvenir in candidats]
    notes = [resultat for resultat in notes if resultat.score >= SEUIL]

    # La recence seule ne suffit pas : sans lien avec la question, un souvenir
    # reste ou il est. Un projet demande explicitement est un lien.
    if not projet:
        notes = [
            resultat for resultat in notes
            if resultat.signaux["correspondance"] > 0 or resultat.signaux["temporel"] > 0
        ]

    notes.sort(key=lambda resultat: resultat.score, reverse=True)

    retenus: List[Resultat] = []
    total = 0
    for resultat in notes:
        cout = len(rendre_ligne(resultat.souvenir)) + 1
        if total + cout > budget_caracteres:
            continue  # un souvenir de plus n'est pas tronque : il n'est pas pris
        retenus.append(resultat)
        total += cout

    logger.debug("Recuperation : %s candidat(s), %s retenu(s), %s caracteres.",
                 len(candidats), len(retenus), total)
    # Ce que le plan courant a REELLEMENT lu, compte ici et nulle part ailleurs :
    # c'est le seul point ou l'on sait combien de souvenirs sont partis vers une
    # invite. Compter les candidats plutot que les retenus gonflerait le chiffre
    # de tout ce que le budget a ecarte — un souvenir non pris n'a pas ete
    # consulte par le modele. Hors plan, `compter_souvenirs_lus` ne fait rien.
    compter_souvenirs_lus(len(retenus))
    return retenus


# --- Rendu ---------------------------------------------------------------------

#: Ce qui precede une deduction d'ARENA. Le modele ne doit pas la lire comme un
#: fait du proprietaire.
MARQUE_SUPPOSITION = "[supposition non confirmee]"


def rendre_ligne(souvenir: Souvenir) -> str:
    """Un souvenir en une ligne, avec sa nature quand elle change la lecture."""
    prefixe = f"{MARQUE_SUPPOSITION} " if souvenir.est_une_supposition else ""
    projet = f"[{souvenir.projet}] " if souvenir.projet else ""
    return f"- {prefixe}{projet}{souvenir.contenu} (source : {souvenir.source})"


def formater(resultats: List[Resultat]) -> str:
    """Le bloc a inserer dans le prompt. Vide, il le dit."""
    if not resultats:
        return "Aucun souvenir pertinent."
    lignes = ["Ce que je sais et qui se rapporte a la demande :"]
    lignes += [rendre_ligne(resultat.souvenir) for resultat in resultats]
    return "\n".join(lignes)


def taille(resultats: List[Resultat]) -> int:
    """Le cout reel en caracteres de ce qui est rendu, marge de titre comprise."""
    return sum(len(rendre_ligne(resultat.souvenir)) + 1 for resultat in resultats)
