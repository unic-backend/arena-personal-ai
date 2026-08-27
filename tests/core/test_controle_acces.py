"""Deux couches, et la plus stricte gagne — toujours.

Le test qui compte le plus est
`test_un_lien_obligatoire_ne_peut_pas_etre_defait_par_la_configuration` : si le
fichier que le proprietaire edite pouvait retirer un coupe-circuit, alors
`PUBLISH: false` ne protegerait plus rien, et il ne le saurait pas.
"""
import pytest
import yaml

from core.permissions.controle import (
    INTERRUPTEURS_OBLIGATOIRES,
    ControleAcces,
)
from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import Decision, PolitiqueDePermissions


@pytest.fixture
def controle_ecrit(tmp_path):
    """Fabrique un controle a partir d'une politique et d'un jeu de booleens."""
    def _fabriquer(services: dict, booleens: dict = None) -> ControleAcces:
        chemin = tmp_path / "politique.yaml"
        chemin.write_text(yaml.safe_dump({"services": services}), encoding="utf-8")
        permissions = PermissionManager(config_path=str(tmp_path / "booleens.yaml"))
        permissions.permissions.update(booleens or {})
        return ControleAcces(
            permissions=permissions, politique=PolitiqueDePermissions(chemin=chemin)
        )
    return _fabriquer


@pytest.fixture
def controle_du_depot():
    """Le controle tel qu'il est reellement livre."""
    return ControleAcces()


# --- La plus stricte gagne ----------------------------------------------------

def test_le_coupe_circuit_eteint_refuse_meme_si_la_politique_autorise(controle_ecrit):
    controle = controle_ecrit(
        {"social": {"publish": {"decision": "ALLOWED", "risque": "HIGH"}}},
        {"PUBLISH": False},
    )

    autorisation = controle.verifier("social", "publish")

    assert autorisation.decision is Decision.REFUSE
    assert autorisation.origine == "coupe-circuit:PUBLISH"


def test_le_coupe_circuit_allume_ne_force_pas_l_autorisation(controle_ecrit):
    """Rallumer l'interrupteur ne transforme pas une CONFIRMATION en ALLOWED."""
    controle = controle_ecrit(
        {"social": {"publish": {"decision": "CONFIRMATION", "risque": "HIGH"}}},
        {"PUBLISH": True},
    )

    assert controle.verifier("social", "publish").demande_confirmation is True


def test_les_deux_couches_levees_laissent_passer(controle_ecrit):
    controle = controle_ecrit(
        {"social": {"publish": {"decision": "ALLOWED", "risque": "HIGH"}}},
        {"PUBLISH": True},
    )

    assert controle.verifier("social", "publish").autorise is True


# --- Le plancher que la configuration ne peut pas entamer ---------------------

def test_un_lien_obligatoire_ne_peut_pas_etre_defait_par_la_configuration(controle_ecrit):
    """La politique n'ecrit aucun `interrupteur` : le plancher s'applique quand meme."""
    controle = controle_ecrit(
        {"social": {"publish": {"decision": "ALLOWED", "risque": "HIGH"}}},
        {"PUBLISH": False},
    )

    assert controle.interrupteur_de("social", "publish") == "PUBLISH"
    assert controle.verifier("social", "publish").refuse is True


@pytest.mark.parametrize("service,action,interrupteur", sorted(
    (s, a, i) for (s, a), i in INTERRUPTEURS_OBLIGATOIRES.items()
))
def test_chaque_lien_obligatoire_tient_sans_configuration(
    controle_ecrit, service, action, interrupteur
):
    controle = controle_ecrit(
        {service: {action: {"decision": "ALLOWED", "risque": "LOW"}}},
        {interrupteur: False},
    )

    assert controle.verifier(service, action).refuse is True


def test_les_trois_interrupteurs_bloquants_couvrent_les_actions_irreversibles():
    """Envoyer, publier, supprimer : chacun a son interrupteur."""
    assert set(INTERRUPTEURS_OBLIGATOIRES.values()) == {"PUBLISH", "SEND_MESSAGES", "DELETE"}


def test_la_configuration_peut_ajouter_un_lien(controle_ecrit):
    """Le plancher n'empeche pas d'en mettre plus."""
    controle = controle_ecrit(
        {"email": {"move": {"decision": "ALLOWED", "risque": "LOW",
                            "interrupteur": "WRITE_FILES"}}},
        {"WRITE_FILES": False},
    )

    assert controle.verifier("email", "move").refuse is True


# --- Les sept booleens qui ne gouvernaient rien -------------------------------

@pytest.mark.parametrize("interrupteur,exemples", [
    ("SEND_MESSAGES", [("email", "send"), ("social", "reply")]),
    ("DELETE", [("email", "delete"), ("calendar", "delete")]),
    ("PUBLISH", [("social", "publish"), ("website", "publish")]),
])
def test_les_booleens_gouvernent_desormais_des_actions(
    controle_du_depot, interrupteur, exemples
):
    """Mesure du 2026-08-27 : sept des neuf n'etaient verifies nulle part."""
    for service, action in exemples:
        assert controle_du_depot.interrupteur_de(service, action) == interrupteur


def test_l_etat_livre_refuse_publication_et_suppression(controle_du_depot):
    """PUBLISH et DELETE sont a false dans le depot : rien ne part."""
    assert controle_du_depot.verifier("social", "publish").refuse is True
    assert controle_du_depot.verifier("email", "delete").refuse is True


def test_l_etat_livre_laisse_lire_et_rediger(controle_du_depot):
    assert controle_du_depot.verifier("email", "read").autorise is True
    assert controle_du_depot.verifier("email", "draft").autorise is True


def test_l_etat_livre_demande_confirmation_pour_envoyer(controle_du_depot):
    """SEND_MESSAGES est a true : le circuit passe, la politique demande l'accord."""
    autorisation = controle_du_depot.verifier("email", "send")

    assert autorisation.demande_confirmation is True
    assert autorisation.origine == "service"


# --- Un refus doit dire ou aller le lever -------------------------------------

def test_un_refus_de_coupe_circuit_nomme_l_interrupteur(controle_ecrit):
    controle = controle_ecrit(
        {"email": {"send": {"decision": "ALLOWED", "risque": "HIGH"}}},
        {"SEND_MESSAGES": False},
    )

    assert controle.verifier("email", "send").origine == "coupe-circuit:SEND_MESSAGES"


def test_un_refus_de_politique_ne_pretend_pas_venir_d_un_interrupteur(controle_ecrit):
    controle = controle_ecrit(
        {"email": {"settings": {"decision": "DENIED", "risque": "HIGH"}}}, {},
    )

    assert controle.verifier("email", "settings").origine == "service"


def test_le_risque_est_conserve_meme_quand_le_coupe_circuit_refuse(controle_ecrit):
    controle = controle_ecrit(
        {"social": {"publish": {"decision": "ALLOWED", "risque": "HIGH"}}},
        {"PUBLISH": False},
    )

    assert controle.verifier("social", "publish").risque.value == "HIGH"


# --- Une action sans interrupteur declare -------------------------------------

def test_une_action_sans_interrupteur_ne_depend_que_de_la_politique(controle_ecrit):
    controle = controle_ecrit(
        {"email": {"read": {"decision": "ALLOWED", "risque": "LOW"}}},
        {"PUBLISH": False, "DELETE": False, "SEND_MESSAGES": False},
    )

    assert controle.interrupteur_de("email", "read") is None
    assert controle.verifier("email", "read").autorise is True


def test_une_action_inconnue_reste_refusee(controle_ecrit):
    controle = controle_ecrit({"email": {}}, {})

    assert controle.verifier("email", "action_inventee").refuse is True


# --- La plateforme branche bien le controle -----------------------------------

def test_la_plateforme_partage_un_seul_controle_d_acces():
    from apps.backend import runtime

    assert runtime.publisher_agent.acces is runtime.acces
    assert runtime.acces.permissions is runtime.permissions


def test_plus_aucune_variable_perm_dans_le_modele_d_environnement():
    """Elles n'etaient lues par personne : les garder invitait a leur faire confiance."""
    from pathlib import Path

    texte = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    for morte in ("PERM_READ_FILES=", "PERM_WRITE_FILES=",
                  "PERM_EXECUTE_COMMANDS=", "PERM_AUTO_PUBLISH="):
        assert morte not in texte


def test_le_modele_d_environnement_renvoie_vers_les_deux_fichiers():
    from pathlib import Path

    texte = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    assert "config/permissions.yaml" in texte
    assert "config/permissions_services.yaml" in texte
