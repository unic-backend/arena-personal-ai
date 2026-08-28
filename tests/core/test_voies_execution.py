"""Les quatre voies : ce qu'une demande a le droit de couter.

Le test que la phase doit passer est
`test_une_question_simple_n_atteint_jamais_le_raisonnement_profond`. Les deux
autres qui comptent verifient que la table ne derive pas de la liste
d'intentions de l'orchestrateur — dans un sens comme dans l'autre.
"""
import pytest

from agents.orchestrator.orchestrator_agent import INTENTIONS
from core.execution.voies import (
    BUDGETS,
    ORDRE,
    VOIE_INCONNUE,
    VOIE_PAR_INTENTION,
    Voie,
    budget_de,
    depasse,
    rang,
    voie_pour,
)

# --- Le test que la phase doit passer ------------------------------------------

def test_une_question_simple_n_atteint_jamais_le_raisonnement_profond():
    voie = voie_pour("CHAT")

    assert voie is not Voie.PROFONDE
    assert voie is not Voie.RECHERCHE
    assert rang(voie) <= rang(Voie.LEGERE)
    assert budget_de(voie).appels_modele_max <= 1, "une passe du modele, pas quatre"


def test_le_raisonnement_profond_est_bien_sur_la_voie_profonde():
    assert voie_pour("DEEP_REASONING") is Voie.PROFONDE


# --- La table ne derive pas de l'orchestrateur ----------------------------------

def test_chaque_intention_de_l_orchestrateur_a_une_voie():
    sans_voie = sorted(INTENTIONS - set(VOIE_PAR_INTENTION))

    assert sans_voie == [], f"intentions sans voie declaree : {sans_voie}"


def test_aucune_voie_ne_designe_une_intention_disparue():
    inconnues = sorted(set(VOIE_PAR_INTENTION) - INTENTIONS)

    assert inconnues == [], f"voies pour des intentions qui n'existent plus : {inconnues}"


# --- Ce qui protege du cout -----------------------------------------------------

def test_une_intention_inconnue_ne_monte_jamais_en_gamme():
    voie = voie_pour("INTENTION_QUI_N_EXISTE_PAS")

    assert voie is VOIE_INCONNUE
    assert rang(voie) < rang(Voie.PROFONDE), "se tromper vers le haut coute la machine"
    assert budget_de(voie).appels_modele_max >= 1, "la voie de repli doit pouvoir repondre"


def test_une_intention_vide_prend_la_voie_de_repli():
    assert voie_pour(None) is VOIE_INCONNUE
    assert voie_pour("") is VOIE_INCONNUE
    assert voie_pour("  chat  ") is Voie.LEGERE, "l'intention est normalisee avant lecture"


@pytest.mark.parametrize("champ", [
    "objectif_secondes", "appels_modele_max", "etapes_outils_max", "memoire_caracteres",
])
def test_les_budgets_croissent_avec_la_voie(champ):
    valeurs = [getattr(BUDGETS[voie], champ) for voie in ORDRE]

    assert valeurs == sorted(valeurs), f"{champ} decroit quelque part : {valeurs}"


def test_seule_la_voie_recherche_sort_sur_le_reseau():
    autorisees = [voie for voie in ORDRE if BUDGETS[voie].reseau_autorise]

    assert autorisees == [Voie.RECHERCHE]


def test_la_voie_instantanee_n_appelle_pas_le_modele():
    assert budget_de(Voie.INSTANTANEE).appels_modele_max == 0


# --- Le controle de depassement -------------------------------------------------

def test_depasse_nomme_la_limite_franchie():
    franchies = depasse(Voie.LEGERE, secondes=30.0, appels_modele=3)

    assert franchies == ["objectif_secondes", "appels_modele_max"]


def test_depasse_est_vide_quand_tout_tient():
    assert depasse(Voie.LEGERE, secondes=2.0, appels_modele=1, etapes_outils=2) == []


def test_une_dimension_non_renseignee_n_est_pas_evaluee():
    assert depasse(Voie.INSTANTANEE) == [], "None n'est pas zero : rien n'est mesure ici"


def test_sortir_sur_le_reseau_hors_recherche_est_un_depassement():
    assert depasse(Voie.PROFONDE, reseau=True) == ["reseau_autorise"]
    assert depasse(Voie.RECHERCHE, reseau=True) == []
