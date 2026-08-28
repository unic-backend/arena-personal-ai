"""Le connecteur GalsenAPI : des chiffres qui gardent leur origine.

Le test que la phase doit passer est `test_chaque_resultat_porte_son_origine` :
une donnee du Senegal qui arriverait sans sa source ne serait qu'une rumeur
bien formatee. Le second qui compte est
`test_ce_connecteur_n_ecrit_rien_et_ne_peut_pas_etre_configure_pour` : la
lecture seule est structurelle, pas un reglage.
"""
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.galsen import ATTRIBUTION, QUOTA_PAR_MINUTE, GalsenConnector

STATISTIQUES = {
    "geographie": {"regions": 14, "departements": 46, "communes": 558},
    "population": {"totale": 18126388, "source_note": "RGPH-5 2023 (ANSD)"},
}
COMMUNES = {
    "count": 2,
    "results": [
        {"id": 53, "nom": "MEDINA", "type": "commune",
         "departement": "SN0101", "population": 82544},
        # Une commune dont l'API ne connait pas la population.
        {"id": 999, "nom": "SANS CHIFFRE", "type": "commune",
         "departement": "SN0101", "population": None},
    ],
}


def faux_appel(reponses, journal=None):
    """Une couche reseau de test : elle note ce qu'on lui demande."""
    def _appeler(chemin, parametres):
        if journal is not None:
            journal.append((chemin, dict(parametres)))
        valeur = reponses.get(chemin)
        if isinstance(valeur, Exception):
            raise valeur
        if valeur is None:
            raise AssertionError(f"chemin non prevu par le test : {chemin}")
        return valeur
    return _appeler


@pytest.fixture
def connecteur():
    return GalsenConnector(appel=faux_appel({
        "statistics/": STATISTIQUES,
        "communes/": COMMUNES,
        "regions/": {"count": 14, "results": []},
    }))


# --- Les deux tests que la phase doit passer -----------------------------------

def test_chaque_resultat_porte_son_origine(connecteur):
    resultat = connecteur.executer("communes", search="Medina")

    assert resultat.statut is Statut.SUCCES
    assert resultat.detail["source"] == ATTRIBUTION
    assert resultat.detail["recupere_le"], "un chiffre sans date n'est pas verifiable"
    assert resultat.preuve, "un succes sans preuve ne se construit pas"


def test_ce_connecteur_n_ecrit_rien_et_ne_peut_pas_etre_configure_pour(connecteur):
    ecritures = [nom for nom, cap in connecteur.capacites().items() if cap.ecriture]

    assert ecritures == [], "une capacite d'ecriture existe : la lecture seule n'est plus structurelle"


# --- La provenance ---------------------------------------------------------------

def test_la_note_de_source_de_l_api_est_conservee(connecteur):
    resultat = connecteur.executer("statistiques")

    assert resultat.detail["source_donnees"] == "RGPH-5 2023 (ANSD)"


def test_un_champ_absent_ne_devient_pas_zero(connecteur):
    resultat = connecteur.executer("communes", search="x")
    sans_chiffre = resultat.detail["donnees"][1]

    assert sans_chiffre["population"] is None, "0 se lirait « personne n'y habite »"


# --- Ce que l'appelant ne peut pas faire -------------------------------------------

def test_une_capacite_non_declaree_n_atteint_jamais_l_api():
    demandes = []
    connecteur = GalsenConnector(appel=faux_appel({"statistics/": STATISTIQUES}, demandes))

    resultat = connecteur.executer("publier_une_region", nom="Dakar")

    assert resultat.statut is not Statut.SUCCES
    assert [c for c, _ in demandes if c != "statistics/"] == [], "l'API a ete appelee"


def test_l_appelant_ne_choisit_pas_l_url():
    demandes = []
    connecteur = GalsenConnector(appel=faux_appel(
        {"statistics/": STATISTIQUES, "communes/": COMMUNES}, demandes))

    connecteur.executer("communes", search="Medina", chemin="../../admin", format="csv")

    envoyes = [p for c, p in demandes if c == "communes/"][0]
    assert envoyes == {"search": "Medina"}, "un parametre non prevu a ete transmis"


# --- La sante ----------------------------------------------------------------------

def test_la_sonde_interroge_l_api_et_ne_suppose_rien():
    connecteur = GalsenConnector(appel=faux_appel({"statistics/": {"autre": 1}}))

    sante = connecteur.sonder()

    assert sante.etat is EtatSante.EN_PANNE
    assert sante.mesure_le, "une sante sans date n'est pas une mesure"


def test_une_panne_reseau_devient_un_etat_pas_une_exception():
    connecteur = GalsenConnector(appel=faux_appel({"statistics/": ConnectionError("coupe")}))

    assert connecteur.sante().etat is EtatSante.EN_PANNE


def test_une_panne_pendant_une_lecture_ne_leve_pas():
    connecteur = GalsenConnector(appel=faux_appel({
        "statistics/": STATISTIQUES,
        "communes/": TimeoutError("trop long"),
    }))

    resultat = connecteur.executer("communes", search="Medina")

    assert resultat.statut is Statut.ECHEC
    assert resultat.preuve is None, "un echec n'exhibe pas de preuve"


def test_la_sonde_est_gardee_une_minute_pour_menager_le_quota():
    demandes = []
    connecteur = GalsenConnector(appel=faux_appel({"statistics/": STATISTIQUES}, demandes))

    connecteur.sonder()
    connecteur.sonder()
    connecteur.sonder()

    assert len(demandes) == 1, "chaque appel re-interrogeait l'API : quota double pour rien"


# --- La politesse ------------------------------------------------------------------

def test_le_quota_annonce_par_l_auteur_est_declare(connecteur):
    quotas = {cap.quota_par_minute for cap in connecteur.capacites().values()}

    assert quotas == {QUOTA_PAR_MINUTE} == {60}
