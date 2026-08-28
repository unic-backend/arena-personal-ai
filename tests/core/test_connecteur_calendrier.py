"""L'agenda : quand est-il libre, et qu'est-ce qui tombe dessus ?

Deux tests portent le chapitre 9.
`test_un_creneau_n_est_libre_que_si_rien_ne_le_chevauche` — un agenda qui
annonce libre un jour occupé envoie quelqu'un sur un chantier où il est déjà
attendu ailleurs.
`test_poser_un_rendez_vous_passe_par_la_confirmation` — écrire dans son agenda
engage une journée de travail.

Aucun test n'appelle Google : la couche réseau et le jeton sont injectés.
"""
from datetime import datetime, timedelta, timezone

import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.calendrier import (
    CREATIONS_PAR_MINUTE,
    QUOTA_PAR_MINUTE,
    CalendrierConnector,
    conflits,
    creneaux_libres,
    lire_occupations,
)

# Lundi 31 août 2026.
LUNDI = datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)
SEMAINE = LUNDI + timedelta(days=5)

CHANTIER = {"summary": "Chantier Medina",
            "start": {"dateTime": "2026-08-31T09:00:00+00:00"},
            "end": {"dateTime": "2026-08-31T12:00:00+00:00"}}
JOURNEE_ENTIERE = {"summary": "Ferie",
                   "start": {"date": "2026-09-01"}, "end": {"date": "2026-09-02"}}
ANNULE = {"summary": "Annule", "status": "cancelled",
          "start": {"dateTime": "2026-08-31T14:00:00+00:00"},
          "end": {"dateTime": "2026-08-31T15:00:00+00:00"}}
SANS_FIN = {"summary": "Sans fin lisible",
            "start": {"dateTime": "2026-09-03T10:00:00+00:00"}, "end": {}}
ILLISIBLE = {"summary": "Illisible", "start": {"dateTime": "pas une date"}, "end": {}}

IDENTIFIANTS = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
AGENDAS = {"items": [{"id": "primary"}]}


def evenements(*liste):
    return {"items": list(liste)}


def faux_appel(reponses, journal=None):
    def _appeler(chemin, parametres, jeton):
        if journal is not None:
            journal.append((chemin, dict(parametres), jeton))
        for cle, valeur in reponses.items():
            if cle in chemin:
                if isinstance(valeur, Exception):
                    raise valeur
                return valeur
        raise AssertionError(f"chemin non prevu par le test : {chemin}")
    return _appeler


def faux_jeton(reponse=None):
    def _echanger(client_id, client_secret, refresh):
        if isinstance(reponse, Exception):
            raise reponse
        return reponse if reponse is not None else {
            "access_token": "jeton-de-test", "expires_in": 3600}
    return _echanger


@pytest.fixture
def configure(monkeypatch):
    for nom in IDENTIFIANTS:
        monkeypatch.setenv(nom, "valeur-de-test")


@pytest.fixture
def connecteur(configure):
    return CalendrierConnector(
        appel=faux_appel({"calendarList": AGENDAS,
                          "events": evenements(CHANTIER, JOURNEE_ENTIERE, ANNULE)}),
        appel_jeton=faux_jeton())


# --- Le test qui porte le chapitre ---------------------------------------------------

def test_un_creneau_n_est_libre_que_si_rien_ne_le_chevauche():
    """Le mardi est pris par un évènement « journée entière » : rien n'y est libre."""
    lecture = lire_occupations([CHANTIER, JOURNEE_ENTIERE])

    libres = creneaux_libres(lecture.occupations, LUNDI, LUNDI + timedelta(days=2),
                             duree_minutes=60)
    jours = {debut.date() for debut, _ in libres}

    assert JOURNEE_ENTIERE["start"]["date"] not in {str(j) for j in jours}
    assert all(debut.date() == LUNDI.date() for debut, _ in libres)


def test_le_creneau_libre_commence_bien_apres_le_rendez_vous():
    lecture = lire_occupations([CHANTIER])

    libres = creneaux_libres(lecture.occupations, LUNDI, LUNDI + timedelta(days=1),
                             duree_minutes=120)

    assert [(d.hour, f.hour) for d, f in libres] == [(12, 18)]


def test_un_creneau_trop_court_n_est_pas_propose():
    """On ne déplace pas une équipe pour trente minutes."""
    lecture = lire_occupations([CHANTIER])

    libres = creneaux_libres(lecture.occupations, LUNDI, LUNDI + timedelta(days=1),
                             duree_minutes=120)

    assert all((fin - debut) >= timedelta(minutes=120) for debut, fin in libres)


def test_rien_n_est_propose_hors_des_heures_ouvrees():
    """3 h du matin serait exact et inutilisable."""
    libres = creneaux_libres([], LUNDI, LUNDI + timedelta(days=1), duree_minutes=60)

    assert all(8 <= debut.hour and fin.hour <= 18 for debut, fin in libres)


def test_le_dimanche_n_est_pas_un_jour_ouvre():
    dimanche = datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc)

    assert creneaux_libres([], dimanche, dimanche + timedelta(hours=23),
                           duree_minutes=60) == []


# --- Ce qui n'est pas deviné -----------------------------------------------------------

def test_un_evenement_annule_ne_prend_rien():
    lecture = lire_occupations([ANNULE])

    assert lecture.occupations == []
    assert lecture.illisibles == 0


def test_un_evenement_illisible_est_compte_pas_oublie():
    """C'est peut-être lui qui remplit la journée qu'on vient d'annoncer libre."""
    lecture = lire_occupations([CHANTIER, ILLISIBLE])

    assert len(lecture.occupations) == 1
    assert lecture.illisibles == 1


def test_un_evenement_sans_fin_bloque_sa_journee_au_lieu_d_etre_un_point():
    lecture = lire_occupations([SANS_FIN])
    jeudi = datetime(2026, 9, 3, 0, 0, tzinfo=timezone.utc)

    libres = creneaux_libres(lecture.occupations, jeudi, jeudi + timedelta(hours=23),
                             duree_minutes=60)

    assert [(d.hour, f.hour) for d, f in libres] == [(8, 10)], (
        "seule la matinee avant l'evenement reste libre")


def test_le_compte_des_illisibles_voyage_avec_la_reponse(configure):
    connecteur = CalendrierConnector(
        appel=faux_appel({"calendarList": AGENDAS,
                          "events": evenements(CHANTIER, ILLISIBLE)}),
        appel_jeton=faux_jeton())

    resultat = connecteur.executer("creneaux", debut=LUNDI, fin=SEMAINE)

    assert resultat.detail["illisibles"] == 1


# --- Les conflits ------------------------------------------------------------------------

def test_un_conflit_nomme_ce_qui_tombe_dessus():
    lecture = lire_occupations([CHANTIER])

    trouves = conflits(lecture.occupations, LUNDI.replace(hour=10), LUNDI.replace(hour=11))

    assert [o.titre for o in trouves] == ["Chantier Medina"]


def test_deux_rendez_vous_bout_a_bout_ne_sont_pas_un_conflit():
    """12 h – 14 h ne chevauche pas 9 h – 12 h."""
    lecture = lire_occupations([CHANTIER])

    assert conflits(lecture.occupations, LUNDI.replace(hour=12),
                    LUNDI.replace(hour=14)) == []


def test_conflits_sans_creneau_propose_ne_verifie_rien(connecteur):
    resultat = connecteur.executer("conflits", debut=LUNDI, fin=SEMAINE)

    assert resultat.statut is Statut.ECHEC
    assert "rien a verifier" in resultat.message


# --- L'écriture ---------------------------------------------------------------------------

def test_poser_un_rendez_vous_passe_par_la_confirmation(connecteur):
    """Écrire dans son agenda engage une journée de travail."""
    poses = []
    connecteur._appel_creation = lambda *a, **k: poses.append(a) or {"id": "pose"}

    resultat = connecteur.executer(
        "creer", titre="Chantier Diamniadio",
        debut=LUNDI.replace(hour=9), fin=LUNDI.replace(hour=12))

    assert resultat.statut is Statut.A_CONFIRMER
    assert not resultat.a_eu_lieu
    assert poses == [], "rien ne doit avoir ete pose dans l'agenda"


def test_un_rendez_vous_confirme_est_pose_et_prouve(connecteur):
    poses = []

    def _poser(chemin, corps, jeton):
        poses.append(corps)
        return {"id": "evenement-1"}

    connecteur._appel_creation = _poser

    resultat = connecteur.executer_confirmee(
        "creer", titre="Chantier Diamniadio", lieu="Diamniadio",
        debut=LUNDI.replace(hour=9), fin=LUNDI.replace(hour=12))

    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve == "evenement-1"
    assert poses[0]["summary"] == "Chantier Diamniadio"
    assert poses[0]["location"] == "Diamniadio"


def test_un_rendez_vous_sans_heure_n_est_pas_pose(connecteur):
    poses = []
    connecteur._appel_creation = lambda *a, **k: poses.append(a) or {"id": "x"}

    resultat = connecteur.executer_confirmee("creer", titre="Chantier")

    assert resultat.statut is Statut.ECHEC
    assert "debut" in resultat.message and "fin" in resultat.message
    assert poses == []


def test_une_fin_avant_le_debut_est_refusee(connecteur):
    resultat = connecteur.executer_confirmee(
        "creer", titre="Chantier", debut=LUNDI.replace(hour=12),
        fin=LUNDI.replace(hour=9))

    assert resultat.statut is Statut.ECHEC
    assert "precede" in resultat.message


def test_une_creation_sans_identifiant_rendu_n_est_pas_prouvee(connecteur):
    connecteur._appel_creation = lambda *a, **k: {"status": "confirmed"}

    resultat = connecteur.executer_confirmee(
        "creer", titre="Chantier", debut=LUNDI.replace(hour=9),
        fin=LUNDI.replace(hour=12))

    assert resultat.statut is Statut.ECHEC
    assert "non prouvee" in resultat.message


def test_la_seule_ecriture_declaree_est_la_creation(connecteur):
    capacites = connecteur.capacites()

    assert set(capacites) == {"lire", "creneaux", "conflits", "creer"}
    assert [nom for nom, c in capacites.items() if c.ecriture] == ["creer"]
    assert capacites["creer"].quota_par_minute == CREATIONS_PAR_MINUTE
    assert capacites["lire"].quota_par_minute == QUOTA_PAR_MINUTE


@pytest.mark.parametrize("interdite", ["modifier", "supprimer", "delete", "reglages"])
def test_modifier_et_supprimer_n_existent_pas(connecteur, interdite):
    assert connecteur.executer(interdite).statut is Statut.NON_IMPLEMENTE


# --- Sans identifiants ---------------------------------------------------------------------

def test_sans_identifiants_l_agenda_n_est_pas_vide(monkeypatch):
    """Un agenda vide se lirait « ta semaine est libre »."""
    for nom in IDENTIFIANTS:
        monkeypatch.delenv(nom, raising=False)
        monkeypatch.delenv(nom.replace("GOOGLE_", "GMAIL_"), raising=False)
    connecteur = CalendrierConnector(appel=faux_appel({}), appel_jeton=faux_jeton())

    sante = connecteur.sante()
    resultat = connecteur.executer("creneaux", debut=LUNDI, fin=SEMAINE)

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "GOOGLE_CLIENT_ID" in sante.message
    assert resultat.statut is Statut.NON_CONFIGURE
    assert resultat.detail.get("donnees") is None


def test_des_identifiants_revoques_ne_valent_pas_une_authentification(configure):
    connecteur = CalendrierConnector(
        appel=faux_appel({}), appel_jeton=faux_jeton(RuntimeError("invalid_grant")))

    assert connecteur.authentifier() is False
    assert connecteur.sante().etat is EtatSante.NON_CONFIGURE


def test_l_agenda_qui_ne_repond_pas_est_une_panne(configure):
    connecteur = CalendrierConnector(
        appel=faux_appel({"calendarList": ConnectionError("injoignable")}),
        appel_jeton=faux_jeton())

    assert connecteur.sante().etat is EtatSante.EN_PANNE


def test_la_fenetre_par_defaut_couvre_la_semaine(configure):
    journal = []
    connecteur = CalendrierConnector(
        appel=faux_appel({"calendarList": AGENDAS, "events": evenements()}, journal),
        appel_jeton=faux_jeton())

    connecteur.executer("creneaux")

    _, parametres, _ = journal[-1]
    debut = datetime.fromisoformat(parametres["timeMin"])
    fin = datetime.fromisoformat(parametres["timeMax"])
    assert (fin - debut).days == 7
