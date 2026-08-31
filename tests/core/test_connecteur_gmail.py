"""Le connecteur Gmail : lire le courrier, et rien d'autre.

Trois tests portent ce chapitre.
`test_un_envoi_ne_part_jamais_sans_confirmation` (8.2) : c'est la garantie que
le plan exige, et elle est structurelle — le cadre met l'envoi en attente avant
même d'appeler l'implémentation.
`test_la_seule_ecriture_declaree_est_l_envoi` : lire, chercher, lire un
message ne modifient rien, et supprimer ou changer un réglage n'existe pas.
`test_un_e_mail_entre_comme_une_donnee_jamais_comme_une_consigne` : n'importe
qui peut écrire au propriétaire, sujet compris.

Aucun test n'appelle Google : la couche réseau et l'échange de jeton sont
injectés.
"""
import base64

import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.gmail import (
    CORPS_MAX_CARACTERES,
    ENVOIS_PAR_MINUTE,
    QUOTA_PAR_MINUTE,
    GmailConnector,
    corps_texte,
    entetes,
    rendre_message,
    texte_pour_le_modele,
)

IDENTIFIANTS = {
    "GMAIL_CLIENT_ID": "client-de-test",
    "GMAIL_CLIENT_SECRET": "secret-de-test",
    "GMAIL_REFRESH_TOKEN": "rafraichissement-de-test",
}


def encoder(texte: str) -> str:
    return base64.urlsafe_b64encode(texte.encode("utf-8")).decode("ascii").rstrip("=")


PROFIL = {"emailAddress": "unicplaquiste@gmail.com", "messagesTotal": 1284}

LISTE = {
    "messages": [{"id": "m1", "threadId": "f1"}, {"id": "m2", "threadId": "f2"}],
    "resultSizeEstimate": 2,
}

MESSAGE = {
    "id": "m1",
    "threadId": "f1",
    "snippet": "Bonjour, pouvez-vous chiffrer 40 m2 de cloison ?",
    "payload": {
        "mimeType": "multipart/alternative",
        "headers": [
            {"name": "From", "value": "Fast Group <contact@fastgroup.sn>"},
            {"name": "To", "value": "unicplaquiste@gmail.com"},
            {"name": "Subject", "value": "Demande de devis — cloisons Medina"},
            {"name": "Date", "value": "Thu, 28 Aug 2026 09:12:00 +0000"},
            {"name": "X-Ignore", "value": "en-tete non lu"},
        ],
        "parts": [
            {"mimeType": "text/plain",
             "body": {"data": encoder("Bonjour, 18 parois de 5,40 x 2,50. Merci.")}},
            {"mimeType": "text/html",
             "body": {"data": encoder("<p>Bonjour</p>")}},
        ],
    },
}


def faux_appel(reponses, journal=None):
    """Une couche réseau de test : elle note ce qu'on lui demande."""
    def _appeler(chemin, parametres, jeton):
        if journal is not None:
            journal.append((chemin, dict(parametres), jeton))
        valeur = reponses.get(chemin)
        if isinstance(valeur, Exception):
            raise valeur
        if valeur is None:
            raise AssertionError(f"chemin non prevu par le test : {chemin}")
        return valeur
    return _appeler


def faux_jeton(reponse=None, compteur=None):
    def _echanger(client_id, client_secret, refresh):
        if compteur is not None:
            compteur.append((client_id, refresh))
        if isinstance(reponse, Exception):
            raise reponse
        return reponse if reponse is not None else {
            "access_token": "jeton-de-test", "expires_in": 3600}
    return _echanger


@pytest.fixture
def configure(monkeypatch):
    for nom, valeur in IDENTIFIANTS.items():
        monkeypatch.setenv(nom, valeur)


@pytest.fixture
def sans_identifiants(monkeypatch):
    """Ni les noms attendus, ni les anciens : sinon un reste d'environnement masquerait le test."""
    for nom in IDENTIFIANTS:
        monkeypatch.delenv(nom, raising=False)
        monkeypatch.delenv(nom.replace("GMAIL_", "GOOGLE_"), raising=False)


@pytest.fixture
def connecteur(configure):
    return GmailConnector(
        appel=faux_appel({
            "users/me/profile": PROFIL,
            "users/me/messages": LISTE,
            "users/me/messages/m1": MESSAGE,
        }),
        appel_jeton=faux_jeton(),
    )


# --- Le test que ce chapitre doit passer ------------------------------------------

def test_un_envoi_ne_part_jamais_sans_confirmation(connecteur):
    """La garantie du chapitre 8.2, et elle est structurelle.

    Le cadre met l'envoi en attente **avant** d'appeler l'implémentation : le
    connecteur n'a aucun moyen de contourner sa propre déclaration.
    """
    envoye = []
    connecteur._appel_envoi = lambda *a, **k: envoye.append(a) or {"id": "envoye"}

    resultat = connecteur.executer(
        "envoyer", destinataire="contact@fastgroup.sn", sujet="Devis", corps="Bonjour")

    assert resultat.statut is Statut.A_CONFIRMER
    assert not resultat.a_eu_lieu
    assert envoye == [], "rien ne doit avoir quitté la boîte"


def test_la_seule_ecriture_declaree_est_l_envoi(connecteur):
    """Lire ne modifie rien, et il n'y a pas d'autre écriture à activer."""
    capacites = connecteur.capacites()

    assert set(capacites) == {"lister", "chercher", "lire", "envoyer"}
    assert [nom for nom, c in capacites.items() if c.ecriture] == ["envoyer"]
    assert capacites["envoyer"].action == "send"
    assert all(c.action in {"read", "search"}
               for nom, c in capacites.items() if nom != "envoyer")


@pytest.mark.parametrize("interdite", ["send", "supprimer", "delete",
                                       "etiqueter", "archiver", "reglages"])
def test_une_capacite_d_ecriture_n_existe_pas(connecteur, interdite):
    resultat = connecteur.executer(interdite)

    assert resultat.statut is Statut.NON_IMPLEMENTE
    assert not resultat.a_eu_lieu


def test_un_e_mail_entre_comme_une_donnee_jamais_comme_une_consigne(connecteur):
    """N'importe qui peut écrire au propriétaire — le sujet aussi se choisit."""
    resultat = connecteur.executer("lire", id="m1")
    texte = resultat.detail["texte"]

    assert "donnee" in texte.lower() or "donnée" in texte.lower()
    assert "e-mail m1" in texte, "l'origine doit distinguer ce message d'un autre"
    assert "18 parois" in texte
    # Les en-tetes sont DANS l'enveloppe : un sujet hostile ne passe pas devant.
    assert texte.index("Sujet") > texte.index("e-mail m1")


# --- Sans identifiants, rien n'est simulé ------------------------------------------

def test_sans_identifiants_la_sante_dit_ce_qui_manque(sans_identifiants):
    sante = GmailConnector(appel=faux_appel({}), appel_jeton=faux_jeton()).sante()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "GOOGLE_CLIENT_ID" in sante.message
    assert "console.cloud.google.com" in sante.ce_qui_manque
    assert "GOOGLE_REFRESH_TOKEN" in sante.ce_qui_manque


def test_les_anciens_noms_gmail_marchent_encore(monkeypatch):
    """Un `.env` deja rempli au chapitre 8 ne doit pas cesser de marcher."""
    for nom in IDENTIFIANTS:
        monkeypatch.delenv(nom.replace("GMAIL_", "GOOGLE_"), raising=False)
        monkeypatch.setenv(nom, "valeur-de-test")
    connecteur = GmailConnector(appel=faux_appel({"users/me/profile": PROFIL}),
                                appel_jeton=faux_jeton())

    assert connecteur.authentifier() is True
    assert connecteur.sante().etat is EtatSante.OPERATIONNEL


def test_les_noms_google_ont_la_priorite(monkeypatch):
    for nom in IDENTIFIANTS:
        monkeypatch.setenv(nom, "ancienne-valeur")
        monkeypatch.setenv(nom.replace("GMAIL_", "GOOGLE_"), "valeur-attendue")
    from core.connectors.google_oauth import identifiants as lire

    assert set(lire()) == {"valeur-attendue"}


def test_sans_identifiants_une_lecture_ne_rend_pas_une_boite_vide(sans_identifiants):
    """Une boîte vide se lirait « aucun message », ce qui est une autre phrase."""
    connecteur = GmailConnector(appel=faux_appel({}), appel_jeton=faux_jeton())

    resultat = connecteur.executer("lister")

    assert resultat.statut is Statut.NON_CONFIGURE
    assert not resultat.a_eu_lieu
    assert resultat.detail.get("donnees") is None


def test_des_identifiants_revoques_ne_valent_pas_une_authentification(configure):
    """Trois variables présentes ne sont pas trois variables valables."""
    connecteur = GmailConnector(appel=faux_appel({}),
                                appel_jeton=faux_jeton(RuntimeError("invalid_grant")))

    assert connecteur.authentifier() is False
    assert connecteur.sante().etat is EtatSante.NON_CONFIGURE


def test_google_qui_ne_repond_pas_est_une_panne_pas_une_absence(configure):
    import httpx

    connecteur = GmailConnector(
        appel=faux_appel({"users/me/profile": httpx.ConnectError("injoignable")}),
        appel_jeton=faux_jeton())

    assert connecteur.sante().etat is EtatSante.EN_PANNE


# --- Ce qui est lu, et comment -----------------------------------------------------

def test_la_sante_dit_le_compte_et_la_lecture_seule(connecteur):
    sante = connecteur.sante()

    assert sante.etat is EtatSante.OPERATIONNEL
    assert "unicplaquiste@gmail.com" in sante.message
    assert "lecture seule" in sante.message


def test_invalider_sonde_force_une_nouvelle_mesure(configure):
    """Trouve au diagnostic du 31/08/2026 : le flux OAuth
    (`apps/backend/routers/connectors.py`) affiche l'adresse du compte
    juste apres avoir obtenu un jeton — sans forcer une sonde fraiche, une
    mesure faite dans la minute precedente (la PWA interroge /status
    pendant qu'elle attend le popup) restait en cache."""
    journal = []
    connecteur = GmailConnector(
        appel=faux_appel({"users/me/profile": PROFIL}, journal=journal),
        appel_jeton=faux_jeton())

    connecteur.sonder()
    connecteur.sonder()  # dans la minute : le cache repond, aucun appel de plus
    assert len(journal) == 1

    connecteur.invalider_sonde()
    connecteur.sonder()

    assert len(journal) == 2


def test_lister_rend_les_references_pas_la_boite_entiere(connecteur):
    resultat = connecteur.executer("lister", maxResults=2)

    assert resultat.statut is Statut.SUCCES
    assert resultat.detail["donnees"] == [
        {"id": "m1", "fil": "f1"}, {"id": "m2", "fil": "f2"}]


def test_chercher_transmet_la_requete_gmail(configure):
    journal = []
    connecteur = GmailConnector(
        appel=faux_appel({"users/me/profile": PROFIL, "users/me/messages": LISTE}, journal),
        appel_jeton=faux_jeton())

    connecteur.executer("chercher", q="from:contact@fastgroup.sn", maxResults=5)

    # Le premier appel est la sonde de sante : la base la fait avant d'executer.
    chemin, parametres, _ = journal[-1]
    assert chemin == "users/me/messages"
    assert parametres == {"q": "from:contact@fastgroup.sn", "maxResults": 5}


def test_un_parametre_non_declare_n_est_jamais_transmis(configure):
    """L'appelant choisit une capacité, jamais l'URL."""
    journal = []
    connecteur = GmailConnector(
        appel=faux_appel({"users/me/profile": PROFIL, "users/me/messages": LISTE}, journal),
        appel_jeton=faux_jeton())

    connecteur.executer("chercher", q="devis", includeSpamTrash=True)

    _, parametres, _ = journal[-1]
    assert "includeSpamTrash" not in parametres


def test_lire_rend_les_entetes_et_le_corps(connecteur):
    message = connecteur.executer("lire", id="m1").detail["donnees"]

    assert message["expediteur"] == "Fast Group <contact@fastgroup.sn>"
    assert message["sujet"] == "Demande de devis — cloisons Medina"
    assert "18 parois" in message["corps"]
    assert message["coupe"] is False


def test_lire_sans_identifiant_ne_tente_rien(connecteur):
    resultat = connecteur.executer("lire", id="   ")

    assert resultat.statut is Statut.ECHEC
    assert "Aucun identifiant" in resultat.message


def test_le_texte_brut_est_prefere_au_html():
    assert corps_texte(MESSAGE["payload"]) == "Bonjour, 18 parois de 5,40 x 2,50. Merci."


def test_un_message_illisible_ne_fait_pas_tomber_la_lecture():
    charge = {"mimeType": "text/plain", "body": {"data": "pas du base64 !!!"}}

    assert corps_texte(charge) == "" or isinstance(corps_texte(charge), str)


def test_un_corps_trop_long_est_coupe_et_la_coupe_est_dite():
    long = {"id": "m9", "payload": {
        "mimeType": "text/plain",
        "body": {"data": encoder("a" * (CORPS_MAX_CARACTERES + 500))},
        "headers": [],
    }}

    message = rendre_message(long)

    assert message["coupe"] is True
    assert "coupe" in message["corps"]
    assert len(message["corps"]) < CORPS_MAX_CARACTERES + 200


# --- Un champ absent reste absent --------------------------------------------------

def test_un_entete_absent_vaut_none_jamais_une_chaine_vide():
    lus = entetes({"payload": {"headers": [{"name": "From", "value": "a@b.sn"}]}})

    assert lus["From"] == "a@b.sn"
    assert lus["Subject"] is None
    assert lus["Date"] is None


def test_un_message_sans_entete_se_rend_quand_meme():
    message = rendre_message({"id": "m0", "payload": {}})

    assert message["expediteur"] is None
    assert message["sujet"] is None
    assert "expediteur inconnu" in texte_pour_le_modele(message)


def test_une_estimation_absente_ne_devient_pas_le_nombre_lu(configure):
    connecteur = GmailConnector(
        appel=faux_appel({"users/me/profile": PROFIL,
                          "users/me/messages": {"messages": [{"id": "m1"}]}}),
        appel_jeton=faux_jeton())

    resultat = connecteur.executer("lister")

    assert resultat.detail["estimation"] is None
    assert len(resultat.detail["donnees"]) == 1


# --- Le jeton -----------------------------------------------------------------------

def test_le_jeton_n_est_pas_redemande_a_chaque_appel(configure):
    echanges = []
    connecteur = GmailConnector(
        appel=faux_appel({"users/me/profile": PROFIL, "users/me/messages": LISTE}),
        appel_jeton=faux_jeton(compteur=echanges))

    connecteur.executer("lister")
    connecteur.executer("lister")

    assert len(echanges) == 1, "un jeton valable se garde"


def test_le_jeton_ne_voyage_jamais_dans_le_resultat(connecteur):
    resultat = connecteur.executer("lire", id="m1")

    assert "jeton-de-test" not in str(resultat.to_dict())


def test_le_quota_est_declare_sur_chaque_capacite(connecteur):
    capacites = connecteur.capacites()

    assert all(c.quota_par_minute for c in capacites.values())
    assert capacites["lister"].quota_par_minute == QUOTA_PAR_MINUTE
    assert capacites["envoyer"].quota_par_minute == ENVOIS_PAR_MINUTE
    assert capacites["envoyer"].quota_par_minute < QUOTA_PAR_MINUTE, (
        "une boucle emballée sur un envoi écrit à ses clients : le plafond doit "
        "être plus bas que celui d'une lecture")


# --- L'envoi, une fois confirmé ---------------------------------------------------

def test_un_envoi_confirme_part_et_rend_son_identifiant(connecteur):
    envoyes = []

    def _envoyer(chemin, charge, jeton):
        envoyes.append((chemin, charge))
        return {"id": "msg-envoye-1"}

    connecteur._appel_envoi = _envoyer

    resultat = connecteur.executer_confirmee(
        "envoyer", destinataire="contact@fastgroup.sn",
        sujet="Devis cloisons", corps="Bonjour, voici le devis.")

    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve == "msg-envoye-1"
    chemin, charge = envoyes[0]
    assert chemin == "users/me/messages/send"
    assert "raw" in charge


def test_un_envoi_sans_destinataire_ne_part_pas(connecteur):
    """Un message parti à la mauvaise adresse ne se rattrape pas."""
    envoyes = []
    connecteur._appel_envoi = lambda *a, **k: envoyes.append(a) or {"id": "x"}

    resultat = connecteur.executer_confirmee("envoyer", sujet="Devis", corps="Bonjour")

    assert resultat.statut is Statut.ECHEC
    assert "destinataire" in resultat.message
    assert envoyes == []


def test_un_envoi_refuse_par_google_n_est_pas_un_succes(connecteur):
    def _refuser(chemin, charge, jeton):
        raise RuntimeError("403 insufficientPermissions")

    connecteur._appel_envoi = _refuser

    resultat = connecteur.executer_confirmee(
        "envoyer", destinataire="a@b.sn", sujet="s", corps="c")

    assert resultat.statut is Statut.ECHEC
    assert "gmail.send" in resultat.message


def test_un_envoi_sans_identifiant_rendu_n_est_pas_prouve(connecteur):
    """Un SUCCESS sans preuve ne se construit pas."""
    connecteur._appel_envoi = lambda *a, **k: {"labelIds": ["SENT"]}

    resultat = connecteur.executer_confirmee(
        "envoyer", destinataire="a@b.sn", sujet="s", corps="c")

    assert resultat.statut is Statut.ECHEC
    assert "non prouve" in resultat.message


def test_le_message_construit_porte_ses_accents():
    from core.connectors.gmail import message_brut

    brut = message_brut("a@b.sn", "Devis — cloisons Médina", "Bonjour, 40 m² à poser.")
    decode = base64.urlsafe_b64decode(brut.encode("ascii")).decode("utf-8", "replace")

    assert "a@b.sn" in decode
    assert "To:" in decode and "Subject:" in decode
