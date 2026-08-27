"""La politique par compte, service, action et risque.

Le test qui compte le plus est `test_une_action_inconnue_est_refusee` : c'est la
seule regle qui ne se configure pas, et c'est elle qui empeche une capacite
nouvelle d'etre autorisee par oubli.

Les neuf booleens historiques ne sont pas touches ici ; un test verifie qu'ils
repondent toujours.
"""
import pytest
import yaml

from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import (
    DECISION_PAR_DEFAUT,
    Autorisation,
    Decision,
    PolitiqueDePermissions,
    Risque,
)


@pytest.fixture(scope="module")
def politique():
    """La politique reellement livree dans le depot."""
    return PolitiqueDePermissions()


@pytest.fixture
def politique_ecrite(tmp_path):
    """Fabrique une politique a partir d'un contenu donne."""
    def _ecrire(contenu: dict) -> PolitiqueDePermissions:
        chemin = tmp_path / "politique.yaml"
        chemin.write_text(yaml.safe_dump(contenu), encoding="utf-8")
        return PolitiqueDePermissions(chemin=chemin)
    return _ecrire


# --- Les defauts que la specification demande ---------------------------------

@pytest.mark.parametrize("action", ["read", "search", "classify", "draft", "summarize"])
def test_lire_et_rediger_un_email_est_autorise(politique, action):
    assert politique.decider("email", action).decision is Decision.AUTORISE


def test_envoyer_un_email_demande_confirmation(politique):
    autorisation = politique.decider("email", "send", compte="unicplaquiste@gmail.com")

    assert autorisation.decision is Decision.CONFIRMATION
    assert autorisation.risque is Risque.ELEVE
    assert autorisation.demande_confirmation is True
    assert autorisation.autorise is False


def test_supprimer_un_email_demande_confirmation(politique):
    """La specification place la suppression en CONFIRMATION, pas en DENIED."""
    assert politique.decider("email", "delete").decision is Decision.CONFIRMATION


def test_changer_les_reglages_du_compte_est_refuse(politique):
    autorisation = politique.decider("email", "settings")

    assert autorisation.decision is Decision.REFUSE
    assert autorisation.refuse is True


@pytest.mark.parametrize("service,action,attendu", [
    ("calendar", "read", Decision.AUTORISE),
    ("calendar", "create", Decision.CONFIRMATION),
    ("calendar", "modify", Decision.CONFIRMATION),
    ("calendar", "delete", Decision.CONFIRMATION),
    ("website", "inspect", Decision.AUTORISE),
    ("website", "analyze", Decision.AUTORISE),
    ("website", "draft", Decision.AUTORISE),
    ("website", "publish", Decision.CONFIRMATION),
    ("website", "delete", Decision.CONFIRMATION),
    ("social", "read", Decision.AUTORISE),
    ("social", "draft", Decision.AUTORISE),
    ("social", "publish", Decision.CONFIRMATION),
])
def test_le_tableau_de_la_specification_est_respecte(politique, service, action, attendu):
    assert politique.decider(service, action).decision is attendu


@pytest.mark.parametrize("service,action", [
    ("email", "send"), ("email", "delete"), ("website", "publish"),
    ("social", "publish"), ("business_profile", "update"),
])
def test_aucune_action_a_effet_externe_n_est_autorisee_sans_rien_demander(
    politique, service, action
):
    assert politique.decider(service, action).autorise is False


# --- La regle qui ne se configure pas -----------------------------------------

def test_une_action_inconnue_est_refusee(politique):
    """Une capacite nouvelle n'est jamais autorisee par oubli."""
    autorisation = politique.decider("email", "action_qui_n_existe_pas")

    assert autorisation.decision is DECISION_PAR_DEFAUT is Decision.REFUSE
    assert autorisation.origine == "defaut"


def test_un_service_inconnu_est_refuse(politique):
    assert politique.decider("service_invente", "read").refuse is True


def test_une_action_inconnue_est_traitee_comme_a_risque_eleve(politique):
    """Ne rien savoir d'une action n'est pas une raison de la croire anodine."""
    assert politique.decider("email", "inconnue").risque is Risque.ELEVE


def test_un_fichier_absent_refuse_tout(tmp_path):
    politique = PolitiqueDePermissions(chemin=tmp_path / "jamais_ecrit.yaml")

    assert politique.decider("email", "read").refuse is True


def test_un_fichier_illisible_refuse_tout(tmp_path):
    chemin = tmp_path / "casse.yaml"
    chemin.write_text("services: [ceci n'est pas: un mapping", encoding="utf-8")

    assert PolitiqueDePermissions(chemin=chemin).decider("email", "read").refuse is True


def test_une_decision_mal_orthographiee_ferme_au_lieu_d_ouvrir(politique_ecrite):
    """Une faute de frappe ne doit jamais devenir une autorisation."""
    politique = politique_ecrite({"services": {"email": {"send": {"decision": "ALOWED"}}}})

    assert politique.decider("email", "send").refuse is True


def test_un_risque_mal_orthographie_devient_eleve(politique_ecrite):
    politique = politique_ecrite(
        {"services": {"email": {"send": {"decision": "ALLOWED", "risque": "moyenne"}}}}
    )

    assert politique.decider("email", "send").risque is Risque.ELEVE


# --- Le plus precis gagne, dans les deux sens ---------------------------------

def test_une_regle_de_compte_peut_ouvrir_plus_que_le_service(politique_ecrite):
    politique = politique_ecrite({
        "services": {"email": {"send": {"decision": "CONFIRMATION", "risque": "HIGH"}}},
        "comptes": {"pro@unic.sn": {"email": {"send": "ALLOWED"}}},
    })

    assert politique.decider("email", "send").demande_confirmation is True
    assert politique.decider("email", "send", compte="pro@unic.sn").autorise is True


def test_une_regle_de_compte_peut_fermer_plus_que_le_service(politique_ecrite):
    politique = politique_ecrite({
        "services": {"email": {"read": {"decision": "ALLOWED", "risque": "LOW"}}},
        "comptes": {"prive@gmail.com": {"email": {"read": "DENIED"}}},
    })

    assert politique.decider("email", "read").autorise is True
    assert politique.decider("email", "read", compte="prive@gmail.com").refuse is True


def test_un_compte_sans_regle_suit_son_service(politique_ecrite):
    politique = politique_ecrite({
        "services": {"email": {"read": {"decision": "ALLOWED", "risque": "LOW"}}},
        "comptes": {"autre@gmail.com": {"email": {"send": "ALLOWED"}}},
    })

    autorisation = politique.decider("email", "read", compte="autre@gmail.com")
    assert autorisation.autorise is True
    assert autorisation.origine == "service"


def test_une_regle_de_compte_s_ecrit_aussi_en_forme_longue(politique_ecrite):
    politique = politique_ecrite({
        "services": {"email": {"send": {"decision": "CONFIRMATION", "risque": "HIGH"}}},
        "comptes": {"pro@unic.sn": {"email": {"send": {"decision": "ALLOWED"}}}},
    })

    assert politique.decider("email", "send", compte="pro@unic.sn").autorise is True


# --- Le risque n'est pas une decision -----------------------------------------

def test_le_risque_reste_celui_du_service_meme_si_le_compte_decide(politique_ecrite):
    """Autoriser une action ne la rend pas anodine : le risque est affiche."""
    politique = politique_ecrite({
        "services": {"email": {"send": {"decision": "CONFIRMATION", "risque": "HIGH"}}},
        "comptes": {"pro@unic.sn": {"email": {"send": "ALLOWED"}}},
    })

    autorisation = politique.decider("email", "send", compte="pro@unic.sn")
    assert autorisation.autorise is True
    assert autorisation.risque is Risque.ELEVE


def test_un_risque_eleve_n_interdit_pas_par_lui_meme(politique_ecrite):
    politique = politique_ecrite(
        {"services": {"x": {"y": {"decision": "ALLOWED", "risque": "HIGH"}}}}
    )

    assert politique.decider("x", "y").autorise is True


# --- Un refus doit pouvoir s'expliquer ----------------------------------------

@pytest.mark.parametrize("compte,attendu", [(None, "service"), ("pro@unic.sn", "compte")])
def test_l_autorisation_dit_quelle_regle_a_tranche(politique_ecrite, compte, attendu):
    politique = politique_ecrite({
        "services": {"email": {"send": {"decision": "CONFIRMATION", "risque": "HIGH"}}},
        "comptes": {"pro@unic.sn": {"email": {"send": "ALLOWED"}}},
    })

    assert politique.decider("email", "send", compte=compte).origine == attendu


def test_l_autorisation_se_lit_en_une_ligne():
    ligne = str(Autorisation(Decision.CONFIRMATION, Risque.ELEVE, "email", "send", "a@b.c", "service"))

    assert ligne == "a@b.c / email · send → CONFIRMATION (risque HIGH)"


def test_la_forme_transportable_porte_les_quatre_axes(politique):
    corps = politique.decider("email", "send", compte="a@b.c").to_dict()

    assert corps == {
        "decision": "CONFIRMATION", "risque": "HIGH", "service": "email",
        "action": "send", "compte": "a@b.c", "origine": "service",
    }


# --- Vue d'ensemble -----------------------------------------------------------

def test_le_resume_couvre_tous_les_services_declares(politique):
    resume = politique.resume()

    assert set(resume) == set(politique.services())
    assert resume["email"]["send"]["decision"] == "CONFIRMATION"


def test_le_resume_applique_les_regles_du_compte(politique_ecrite):
    politique = politique_ecrite({
        "services": {"email": {"send": {"decision": "CONFIRMATION", "risque": "HIGH"}}},
        "comptes": {"pro@unic.sn": {"email": {"send": "ALLOWED"}}},
    })

    assert politique.resume("pro@unic.sn")["email"]["send"]["decision"] == "ALLOWED"


def test_recharger_prend_en_compte_une_modification(tmp_path):
    chemin = tmp_path / "politique.yaml"
    chemin.write_text(yaml.safe_dump(
        {"services": {"email": {"send": {"decision": "CONFIRMATION", "risque": "HIGH"}}}}
    ), encoding="utf-8")
    politique = PolitiqueDePermissions(chemin=chemin)
    assert politique.decider("email", "send").demande_confirmation is True

    chemin.write_text(yaml.safe_dump(
        {"services": {"email": {"send": {"decision": "DENIED", "risque": "HIGH"}}}}
    ), encoding="utf-8")
    politique.recharger()

    assert politique.decider("email", "send").refuse is True


# --- Les neuf booleens historiques repondent toujours -------------------------

@pytest.mark.parametrize("nom,attendu", [
    ("READ_FILES", True), ("WRITE_FILES", True), ("SEARCH_WEB", True),
    ("EXECUTE_COMMANDS", False), ("PUBLISH", False), ("DELETE", False),
])
def test_les_booleens_historiques_ne_sont_pas_touches(nom, attendu):
    """Ce module ajoute une couche ; il n'en retire aucune."""
    assert PermissionManager().is_allowed(nom) is attendu
