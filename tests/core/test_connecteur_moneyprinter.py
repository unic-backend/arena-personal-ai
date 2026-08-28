"""MoneyPrinterTurbo : une vidéo courte à partir d'un sujet.

Le contrat n'est pas deviné, il est lu dans le dépôt du projet :
`router.prefix = "/api/v1"`, `POST /videos`, `GET /tasks/{task_id}`, les états
-1 / 1 / 4 de `app/models/const.py`, et le jeton dans l'en-tête `x-api-key`.

Deux tests portent l'intégration.
`test_une_generation_ne_part_jamais_sans_confirmation` — elle occupe sa carte
graphique plusieurs minutes, et c'est lui qui décide de la dépenser.
`test_l_etat_est_traduit_dans_la_forme_que_le_suivi_sait_lire` — c'est ce qui
permet de réutiliser le suivi déjà écrit pour WanGP au lieu d'en écrire un second.

Aucun test n'appelle le service : la couche réseau est injectée.
"""
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.moneyprinter import (
    GENERATIONS_PAR_MINUTE,
    TACHE_ECHOUEE,
    TACHE_EN_COURS,
    TACHE_TERMINEE,
    MoneyPrinterConnector,
    instantane_de,
)

TACHES = {"data": {"tasks": [{"task_id": "t1", "state": TACHE_TERMINEE}], "total": 1}}
EN_COURS = {"data": {"task_id": "t1", "state": TACHE_EN_COURS, "progress": 40}}
TERMINEE = {"data": {"task_id": "t1", "state": TACHE_TERMINEE, "progress": 100,
                     "combined_videos": ["/videos/t1/final.mp4"]}}
ECHOUEE = {"data": {"task_id": "t1", "state": TACHE_ECHOUEE, "progress": 20,
                    "failed_stage": "materials", "error": "aucune video trouvee"}}


def faux_get(reponses, journal=None):
    def _appeler(chemin, parametres, jeton):
        if journal is not None:
            journal.append(("GET", chemin, dict(parametres), jeton))
        for cle, valeur in reponses.items():
            if chemin.startswith(cle):
                if isinstance(valeur, Exception):
                    raise valeur
                return valeur
        raise AssertionError(f"chemin non prevu : {chemin}")
    return _appeler


def faux_post(reponse=None, journal=None):
    def _appeler(chemin, charge, jeton):
        if journal is not None:
            journal.append(("POST", chemin, dict(charge), jeton))
        if isinstance(reponse, Exception):
            raise reponse
        return reponse if reponse is not None else {"data": {"task_id": "t1"}}
    return _appeler


@pytest.fixture
def connecteur():
    return MoneyPrinterConnector(
        appel=faux_get({"tasks/t1": EN_COURS, "tasks": TACHES}),
        appel_generation=faux_post(), jeton="")


# --- Les deux tests qui portent l'intégration -------------------------------------

def test_une_generation_ne_part_jamais_sans_confirmation(connecteur):
    """Elle occupe la carte graphique plusieurs minutes : c'est lui qui décide."""
    journal = []
    connecteur._appel_generation = faux_post(journal=journal)

    resultat = connecteur.executer("generer", sujet="les cloisons BA13")

    assert resultat.statut is Statut.A_CONFIRMER
    assert not resultat.a_eu_lieu
    assert journal == [], "aucune generation ne doit avoir demarre"


def test_l_etat_est_traduit_dans_la_forme_que_le_suivi_sait_lire():
    """Réutiliser le suivi de WanGP plutôt que d'en écrire un second."""
    instantane = instantane_de(TERMINEE["data"])

    assert instantane["done"] is True
    assert instantane["result"]["success"] is True
    assert instantane["result"]["generated_files"] == ["/videos/t1/final.mp4"]


def test_le_suivi_deja_ecrit_lit_reellement_cet_instantane():
    """La preuve par l'usage : `suivi_video` n'a pas été touché."""
    import asyncio

    from core.connectors.suivi_video import suivre_generation

    connecteur = MoneyPrinterConnector(
        appel=faux_get({"tasks/t1": TERMINEE, "tasks": TACHES}),
        appel_generation=faux_post(), jeton="")

    suivi = asyncio.run(suivre_generation(connecteur, "t1", intervalle=0))

    assert suivi.reussi is True
    assert suivi.fichiers == ["/videos/t1/final.mp4"]


# --- La progression vient du service, jamais d'une estimation -----------------------

def test_la_progression_vient_du_champ_du_service():
    instantane = instantane_de(EN_COURS["data"])

    assert instantane["done"] is False
    assert instantane["result"]["total_tasks"] == 100
    assert instantane["result"]["successful_tasks"] == 40


def test_une_progression_absente_reste_absente():
    """Un total inconnu ne devient pas zéro, ni cent."""
    instantane = instantane_de({"state": TACHE_EN_COURS})

    assert "total_tasks" not in instantane["result"]
    assert "successful_tasks" not in instantane["result"]


def test_une_tache_terminee_sans_fichier_n_est_pas_une_reussite():
    """Une vidéo annoncée prête sans fichier n'est pas une vidéo."""
    instantane = instantane_de({"state": TACHE_TERMINEE, "combined_videos": []})

    assert instantane["done"] is True
    assert instantane["result"]["success"] is False


def test_un_echec_porte_sa_raison():
    instantane = instantane_de(ECHOUEE["data"])

    assert instantane["done"] is True
    assert instantane["result"]["success"] is False
    assert "aucune video trouvee" in instantane["result"]["errors"][0]


def test_un_echec_sans_message_nomme_l_etape():
    instantane = instantane_de({"state": TACHE_ECHOUEE, "failed_stage": "audio"})

    assert "audio" in instantane["result"]["errors"][0]


# --- Ce qui part au service ----------------------------------------------------------

def test_la_generation_confirmee_envoie_le_sujet_et_le_format(connecteur):
    journal = []
    connecteur._appel_generation = faux_post(journal=journal)

    resultat = connecteur.executer_confirmee("generer", sujet="les cloisons BA13")

    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve == "t1"
    _, chemin, charge, _ = journal[0]
    assert chemin == "videos"
    assert charge["video_subject"] == "les cloisons BA13"
    assert charge["video_aspect"] == "9:16"
    assert charge["subtitle_enabled"] is True


def test_une_generation_sans_sujet_ne_part_pas(connecteur):
    journal = []
    connecteur._appel_generation = faux_post(journal=journal)

    resultat = connecteur.executer_confirmee("generer", sujet="   ")

    assert resultat.statut is Statut.ECHEC
    assert journal == []


def test_une_generation_sans_identifiant_rendu_n_est_pas_prouvee(connecteur):
    connecteur._appel_generation = faux_post({"data": {}})

    resultat = connecteur.executer_confirmee("generer", sujet="le placo")

    assert resultat.statut is Statut.ECHEC
    assert "sans rendre d'identifiant" in resultat.message


def test_le_jeton_part_dans_l_entete_et_pas_dans_le_resultat():
    journal = []
    connecteur = MoneyPrinterConnector(
        appel=faux_get({"tasks": TACHES}, journal),
        appel_generation=faux_post(journal=journal), jeton="jeton-secret")

    resultat = connecteur.executer_confirmee("generer", sujet="le placo")

    assert any(entree[-1] == "jeton-secret" for entree in journal)
    assert "jeton-secret" not in str(resultat.to_dict())


# --- Service éteint ---------------------------------------------------------------------

def test_le_service_eteint_donne_la_commande_de_lancement():
    connecteur = MoneyPrinterConnector(
        appel=faux_get({"tasks": ConnectionError("refuse")}),
        appel_generation=faux_post(), jeton="")

    sante = connecteur.sante()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "uvicorn app.asgi:app" in sante.ce_qui_manque
    assert "8080" in sante.ce_qui_manque


def test_sans_service_aucune_video_n_est_promise():
    connecteur = MoneyPrinterConnector(
        appel=faux_get({"tasks": ConnectionError("refuse")}),
        appel_generation=faux_post(), jeton="")

    resultat = connecteur.executer_confirmee("generer", sujet="le placo")

    assert resultat.statut is Statut.NON_CONFIGURE
    assert not resultat.a_eu_lieu


def test_l_etat_sans_identifiant_ne_regarde_rien(connecteur):
    resultat = connecteur.executer("etat_travail", job_id="  ")

    assert resultat.statut is Statut.ECHEC
    assert "Aucun identifiant" in resultat.message


def test_la_seule_ecriture_declaree_est_la_generation(connecteur):
    capacites = connecteur.capacites()

    assert set(capacites) == {"generer", "etat_travail", "taches"}
    assert [nom for nom, c in capacites.items() if c.ecriture] == ["generer"]
    assert capacites["generer"].quota_par_minute == GENERATIONS_PAR_MINUTE


@pytest.mark.parametrize("interdite", ["supprimer", "delete", "annuler_travail"])
def test_supprimer_une_tache_n_existe_pas(connecteur, interdite):
    assert connecteur.executer(interdite).statut is Statut.NON_IMPLEMENTE
