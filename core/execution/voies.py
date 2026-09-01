"""Les quatre voies d'execution, et ce que chacune a le droit de couter.

L'aiguillage existe deja : `agents/orchestrator` classe la demande en une
intention parmi quatorze. Ce qui n'existait pas, c'est le lien entre une
intention et le cout qu'elle autorise. Sans ce lien, « bonjour » et « demontre
cette integrale » traversent la meme machinerie, et le premier paie le prix du
second.

Ce module ne classe rien et n'execute rien. Il declare, en un seul endroit :
quelle intention emprunte quelle voie, et ce que chaque voie s'autorise.

**Quatre regles :**

1. **Une question simple n'atteint jamais le raisonnement profond.** `CHAT`
   emprunte une voie legere, et aucune configuration ne la fait monter.

2. **Une intention inconnue prend la voie la moins chere qui puisse repondre**
   — jamais la plus puissante. Se tromper vers le haut coute une carte
   graphique occupee et une minute d'attente ; se tromper vers le bas coute une
   reponse moins bonne, et cela se voit.

3. **Les budgets croissent avec la voie, sur toutes les dimensions.** Une voie
   plus profonde qui s'autoriserait moins que la precedente serait une erreur
   de table, pas un reglage.

4. **`objectif_secondes` est une cible, pas une mesure.** Rien ici n'a ete
   chronometre ; c'est la phase 7.2 qui mesurera. Une cible non tenue est une
   information, pas un mensonge — a condition de ne jamais la presenter comme
   un resultat.
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger("usman.execution.voies")


class Voie(str, Enum):
    """Les quatre regimes d'execution, du moins cher au plus cher."""

    INSTANTANEE = "INSTANT"   # aucune generation : la reponse se construit sur place
    LEGERE = "LIGHT"          # une passe du modele rapide
    PROFONDE = "DEEP"         # modele profond, plusieurs passes, aucun acces reseau
    RECHERCHE = "RESEARCH"    # plusieurs etapes, et le droit de sortir sur le reseau


#: L'ordre est la definition de « plus cher ». Il sert au controle de coherence
#: des budgets et au choix de repli.
ORDRE: List[Voie] = [Voie.INSTANTANEE, Voie.LEGERE, Voie.PROFONDE, Voie.RECHERCHE]


def rang(voie: Voie) -> int:
    """La position d'une voie dans l'ordre des couts. 0 est la moins chere."""
    return ORDRE.index(voie)


@dataclass(frozen=True)
class Budget:
    """Ce qu'une voie s'autorise.

    Attributes:
        objectif_secondes: la cible de duree. **Une cible, pas une mesure.**
        appels_modele_max: combien de fois le modele peut etre appele.
        etapes_outils_max: combien d'appels d'outils la voie s'autorise.
        memoire_caracteres: ce que la memoire peut ajouter au prompt.
        reseau_autorise: si la voie a le droit de sortir de la machine.
    """

    objectif_secondes: float
    appels_modele_max: int
    etapes_outils_max: int
    memoire_caracteres: int
    reseau_autorise: bool


#: Les budgets. Ils croissent avec le rang, et un test le verifie — une table
#: qui se contredit est une panne silencieuse, pas un reglage discutable.
BUDGETS: Dict[Voie, Budget] = {
    Voie.INSTANTANEE: Budget(
        objectif_secondes=0.5, appels_modele_max=0, etapes_outils_max=0,
        memoire_caracteres=500, reseau_autorise=False,
    ),
    Voie.LEGERE: Budget(
        objectif_secondes=8.0, appels_modele_max=1, etapes_outils_max=2,
        memoire_caracteres=2000, reseau_autorise=False,
    ),
    Voie.PROFONDE: Budget(
        objectif_secondes=60.0, appels_modele_max=4, etapes_outils_max=6,
        memoire_caracteres=3000, reseau_autorise=False,
    ),
    Voie.RECHERCHE: Budget(
        objectif_secondes=180.0, appels_modele_max=6, etapes_outils_max=20,
        memoire_caracteres=3000, reseau_autorise=True,
    ),
}

#: L'aiguillage, intention par intention. La liste des intentions appartient a
#: `agents/orchestrator` ; un test verifie que les deux ne divergent pas — ni
#: une intention sans voie, ni une voie pour une intention qui n'existe plus.
VOIE_PAR_INTENTION: Dict[str, Voie] = {
    # Conversation et metier : une passe du modele rapide suffit.
    "CHAT": Voie.LEGERE,
    "PLAQUISTE": Voie.LEGERE,
    "CODE_EXECUTION": Voie.LEGERE,
    "RAG_DOCS": Voie.LEGERE,
    # Ecrire une publication est une redaction soignee, relue puis corrigee :
    # plusieurs passes sur la machine, sans sortir.
    "SOCIAL": Voie.PROFONDE,
    # Plusieurs passes, sur la machine, sans sortir.
    "GRAPHRAG": Voie.PROFONDE,
    "STUDIO": Voie.PROFONDE,
    "VIDEO_ANALYSIS": Voie.PROFONDE,
    "VISION": Voie.PROFONDE,
    # Un plan de montage est un JSON structure a produire d un coup et
    # relu : plusieurs passes sur la machine, jamais un aller dehors.
    "MONTAGE": Voie.PROFONDE,
    "SWE_FIX": Voie.PROFONDE,
    "REPO_ENGINEERING": Voie.PROFONDE,
    "DEEP_REASONING": Voie.PROFONDE,
    # Ce qui doit aller chercher dehors. Le courrier en fait partie : la boite
    # n'est pas sur la machine, et RECHERCHE est la seule voie qui autorise a
    # en sortir. Lire cinq messages est aussi, reellement, plusieurs etapes.
    "EMAIL": Voie.RECHERCHE,
    "FRESH_INFO": Voie.RECHERCHE,
    "TREND_SEARCH": Voie.RECHERCHE,
    "DEEP_RESEARCH": Voie.RECHERCHE,
    "BROWSER": Voie.RECHERCHE,
}

#: Voie d'une intention inconnue. La moins chere **qui puisse encore repondre** :
#: `INSTANTANEE` n'appelle pas le modele et ne repondrait rien du tout.
VOIE_INCONNUE = Voie.LEGERE


def voie_pour(intention: Optional[str]) -> Voie:
    """La voie d'une intention. Une intention inconnue ne monte jamais en gamme."""
    if not intention:
        return VOIE_INCONNUE
    voie = VOIE_PAR_INTENTION.get(intention.strip().upper())
    if voie is None:
        logger.info("Intention inconnue (%s) : voie %s par defaut.",
                    intention, VOIE_INCONNUE.value)
        return VOIE_INCONNUE
    return voie


def budget_de(voie: Voie) -> Budget:
    """Le budget d'une voie."""
    return BUDGETS[voie]


def depasse(
    voie: Voie,
    secondes: Optional[float] = None,
    appels_modele: Optional[int] = None,
    etapes_outils: Optional[int] = None,
    caracteres_memoire: Optional[int] = None,
    reseau: bool = False,
) -> List[str]:
    """Les limites franchies, nommees. Une liste vide veut dire : dans les clous.

    Rendre les noms plutot qu'un booleen, parce que « ca a depasse » n'aide
    personne : ce qu'il faut savoir, c'est **quoi**.

    Une dimension non renseignee n'est pas evaluee — `None` n'est pas zero.
    """
    budget = BUDGETS[voie]
    franchies: List[str] = []
    if secondes is not None and secondes > budget.objectif_secondes:
        franchies.append("objectif_secondes")
    if appels_modele is not None and appels_modele > budget.appels_modele_max:
        franchies.append("appels_modele_max")
    if etapes_outils is not None and etapes_outils > budget.etapes_outils_max:
        franchies.append("etapes_outils_max")
    if caracteres_memoire is not None and caracteres_memoire > budget.memoire_caracteres:
        franchies.append("memoire_caracteres")
    if reseau and not budget.reseau_autorise:
        franchies.append("reseau_autorise")
    return franchies
