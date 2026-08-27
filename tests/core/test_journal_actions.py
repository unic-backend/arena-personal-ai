"""Le journal : neuf champs qui reviennent intacts, et aucun secret dedans.

Deux garanties comptent plus que les autres, et elles sont testees par
sabotage dans le rapport de phase :

- un aller-retour SQLite ne perd ni ne deforme un seul champ ;
- une valeur dont le nom annonce un secret n'atteint jamais le disque.
"""
import json
import sqlite3

import pytest

from core.actions.journal import (
    MASQUE,
    ActionEnregistree,
    EtatVerification,
    JournalDesActions,
    masquer,
)
from core.actions.resultat import (
    a_confirmer,
    echec,
    non_configure,
    non_implemente,
    refuse,
    succes,
)


@pytest.fixture
def journal(tmp_path):
    return JournalDesActions(db_path=str(tmp_path / "journal.db"))


@pytest.fixture
def action():
    return ActionEnregistree(
        outil="gmail",
        action="send",
        cible="client@example.com",
        resultat="SUCCESS",
        niveau_permission="CONFIRMATION",
        parametres={"objet": "Devis UC-2026-0827", "pieces_jointes": 1},
        erreurs=None,
        verification=EtatVerification.VERIFIEE,
        preuve="msg-id-42",
    )


# --- L'aller-retour -----------------------------------------------------------

def test_les_neuf_champs_reviennent_intacts(journal, action):
    assert journal.enregistrer(action) is True

    relue = journal.lire(action.identifiant)

    assert relue.to_dict() == action.to_dict()


def test_chaque_champ_pris_un_par_un(journal, action):
    journal.enregistrer(action)
    relue = journal.lire(action.identifiant)

    assert relue.identifiant == action.identifiant
    assert relue.horodatage == action.horodatage
    assert relue.outil == "gmail"
    assert relue.action == "send"
    assert relue.cible == "client@example.com"
    assert relue.parametres == {"objet": "Devis UC-2026-0827", "pieces_jointes": 1}
    assert relue.niveau_permission == "CONFIRMATION"
    assert relue.resultat == "SUCCESS"
    assert relue.erreurs is None
    assert relue.verification is EtatVerification.VERIFIEE
    assert relue.preuve == "msg-id-42"


def test_une_erreur_revient_telle_quelle(journal):
    action = ActionEnregistree(
        outil="gmail", action="send", cible="x@y.z", resultat="FAILED",
        erreurs="Connection refused after 3 attempts",
    )
    journal.enregistrer(action)

    assert journal.lire(action.identifiant).erreurs == "Connection refused after 3 attempts"


def test_des_parametres_imbriques_survivent(journal):
    parametres = {"destinataires": ["a@b.c", "d@e.f"], "options": {"copie": True, "essais": 3}}
    action = ActionEnregistree(
        outil="gmail", action="send", cible="a@b.c", resultat="SUCCESS",
        parametres=parametres, preuve="id-1",
    )
    journal.enregistrer(action)

    assert journal.lire(action.identifiant).parametres == parametres


def test_les_accents_survivent(journal):
    action = ActionEnregistree(
        outil="plaquiste", action="devis", cible="Chantier Médina",
        resultat="SUCCESS", parametres={"objet": "Cloison fermée deux faces"},
        preuve="UC-2026-0827-MED",
    )
    journal.enregistrer(action)

    relue = journal.lire(action.identifiant)
    assert relue.cible == "Chantier Médina"
    assert relue.parametres["objet"] == "Cloison fermée deux faces"


def test_un_identifiant_inconnu_rend_none(journal):
    assert journal.lire("jamais-ecrit") is None


def test_chaque_action_recoit_un_identifiant_unique():
    identifiants = {
        ActionEnregistree(outil="o", action="a", cible="c", resultat="FAILED").identifiant
        for _ in range(200)
    }

    assert len(identifiants) == 200


# --- Les secrets ne touchent pas le disque ------------------------------------

@pytest.mark.parametrize("nom", [
    "password", "PASSWORD", "mot_de_passe", "api_key", "USMAN_API_KEY",
    "access_token", "refresh_token", "jeton_oauth", "client_secret",
    "Authorization", "credential", "private_key", "cookie", "session_key",
])
def test_un_champ_qui_annonce_un_secret_est_masque(nom):
    action = ActionEnregistree(
        outil="gmail", action="send", cible="x", resultat="FAILED",
        parametres={nom: "valeur-tres-secrete-42"},
    )

    assert action.parametres[nom] == MASQUE
    assert "valeur-tres-secrete-42" not in json.dumps(action.parametres)


def test_le_masquage_descend_dans_les_structures_imbriquees():
    masques = masquer({"compte": {"nom": "ousmane", "oauth": {"access_token": "abc123"}}})

    assert masques["compte"]["oauth"]["access_token"] == MASQUE
    assert masques["compte"]["nom"] == "ousmane"


def test_le_masquage_traverse_les_listes():
    masques = masquer({"comptes": [{"api_key": "k1"}, {"api_key": "k2"}]})

    assert [c["api_key"] for c in masques["comptes"]] == [MASQUE, MASQUE]


def test_aucun_secret_n_atteint_le_fichier_sqlite(journal, tmp_path):
    """Le test qui compte : on relit le fichier brut, pas l'objet."""
    action = ActionEnregistree(
        outil="gmail", action="send", cible="x", resultat="FAILED",
        parametres={"access_token": "ya29.SECRET-A-NE-PAS-ECRIRE"},
    )
    journal.enregistrer(action)

    brut = journal.db_path.read_bytes()

    assert b"ya29.SECRET-A-NE-PAS-ECRIRE" not in brut
    assert MASQUE.encode() in brut


def test_un_champ_anodin_n_est_pas_masque():
    action = ActionEnregistree(
        outil="gmail", action="send", cible="x", resultat="FAILED",
        parametres={"objet": "Bonjour", "destinataire": "client@example.com"},
    )

    assert action.parametres["objet"] == "Bonjour"
    assert action.parametres["destinataire"] == "client@example.com"


def test_une_valeur_enorme_est_tronquee():
    action = ActionEnregistree(
        outil="gmail", action="send", cible="x", resultat="FAILED",
        parametres={"corps": "a" * 10_000},
    )

    assert len(action.parametres["corps"]) < 10_000
    assert action.parametres["corps"].endswith("[tronque]")


# --- Le journal ne peut pas contredire l'action -------------------------------

def test_un_succes_est_journalise_verifie_avec_sa_preuve():
    resultat = succes("publish_video", "TikTok", "Publiee.", "https://tiktok.com/v/9")

    entree = ActionEnregistree.depuis_resultat(resultat, outil="tiktok")

    assert entree.resultat == "SUCCESS"
    assert entree.verification is EtatVerification.VERIFIEE
    assert entree.preuve == "https://tiktok.com/v/9"


@pytest.mark.parametrize("fabrique", [
    lambda: non_configure("publish_video", "TikTok", "un jeton"),
    lambda: refuse("publish_video", "TikTok", "PUBLISH"),
    lambda: a_confirmer("send", "client@example.com", "pret"),
    lambda: non_implemente("delete", "Gmail", "pas de chemin"),
])
def test_une_action_jamais_tentee_a_une_verification_sans_objet(fabrique):
    """« Non verifiee » laisserait croire a un doute ; il n'y a pas de doute."""
    entree = ActionEnregistree.depuis_resultat(fabrique(), outil="tiktok")

    assert entree.verification is EtatVerification.SANS_OBJET
    assert entree.preuve is None


def test_un_echec_reste_non_verifie():
    """Une tentative a eu lieu : on ne sait pas ce qu'elle a laisse derriere."""
    entree = ActionEnregistree.depuis_resultat(
        echec("send", "client@example.com", "coupure reseau"), outil="gmail"
    )

    assert entree.resultat == "FAILED"
    assert entree.verification is EtatVerification.NON_VERIFIEE


def test_le_resultat_journalise_est_toujours_celui_de_l_action():
    for fabrique in (
        lambda: succes("a", "b", "ok", "p"),
        lambda: echec("a", "b", "non"),
        lambda: non_configure("a", "b", "x"),
        lambda: refuse("a", "b", "PUBLISH"),
    ):
        resultat = fabrique()
        assert ActionEnregistree.depuis_resultat(resultat, "outil").resultat == resultat.statut.value


def test_les_parametres_passes_au_journal_sont_masques_aussi():
    entree = ActionEnregistree.depuis_resultat(
        refuse("send", "x", "SEND_MESSAGES"), outil="gmail",
        parametres={"api_key": "secret"},
    )

    assert entree.parametres["api_key"] == MASQUE


# --- Lecture ------------------------------------------------------------------

def test_les_actions_reviennent_de_la_plus_recente_a_la_plus_ancienne(journal):
    for index in range(5):
        journal.enregistrer(ActionEnregistree(
            outil="gmail", action="send", cible=f"cible-{index}", resultat="FAILED",
            horodatage=f"2026-08-2{index}T10:00:00+00:00",
        ))

    assert [a.cible for a in journal.dernieres()] == [f"cible-{i}" for i in (4, 3, 2, 1, 0)]


def test_la_lecture_peut_se_limiter_a_une_cible(journal):
    journal.enregistrer(ActionEnregistree(outil="o", action="a", cible="TikTok", resultat="FAILED"))
    journal.enregistrer(ActionEnregistree(outil="o", action="a", cible="Gmail", resultat="FAILED"))

    assert [a.cible for a in journal.dernieres(cible="Gmail")] == ["Gmail"]


def test_la_limite_est_respectee(journal):
    for index in range(10):
        journal.enregistrer(ActionEnregistree(
            outil="o", action="a", cible=f"c{index}", resultat="FAILED"))

    assert len(journal.dernieres(limite=3)) == 3


def test_un_journal_vide_rend_une_liste_vide(journal):
    assert journal.dernieres() == []


# --- Le journal ne fait pas tomber l'action -----------------------------------

def test_une_ecriture_impossible_rend_false_sans_lever(journal, action, monkeypatch):
    """Empecher un envoi parce que sa trace a echoue serait pire que la perdre."""
    def connexion_cassee():
        raise sqlite3.OperationalError("disque plein")

    monkeypatch.setattr(journal, "_connexion", connexion_cassee)

    assert journal.enregistrer(action) is False


def test_la_table_est_creee_a_la_demande(tmp_path):
    chemin = tmp_path / "sous" / "dossier" / "journal.db"

    JournalDesActions(db_path=str(chemin))

    assert chemin.exists()
