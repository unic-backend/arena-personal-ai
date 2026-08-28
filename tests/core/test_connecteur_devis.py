"""Le devis UniC Plaquiste : chiffrer librement, ecrire seulement sur accord.

Deux tests portent l'integration.
`test_produire_ne_part_jamais_sans_confirmation` : un devis est un document qui
part chez un client, il ne s'ecrit pas parce qu'une phrase y ressemblait.
`test_un_devis_produit_laisse_un_fichier_qui_est_sa_preuve` : le succes est le
PDF sur le disque, jamais l'intention de l'ecrire.

Le troisieme qui compte est `test_sans_destinataire_rien_n_est_produit` : un
devis adresse a la mauvaise personne est pire qu'un devis absent.
"""
import pytest

from agents.plaquiste.plaquiste_agent import charger_metier
from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.devis import DevisConnector, lignes_depuis

#: La demande de son devis de reference UC-2026-0804-FG2.
DEMANDE = "18 parois de 5,40 x 2,50 m"

DESTINATAIRE = {"client": "Fast Group", "lieu": "Medina", "objet": "cloisons BA13"}


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "devis"


@pytest.fixture
def connecteur(dossier):
    return DevisConnector(dossier=dossier)


def fichiers(dossier):
    """Ce que le dossier de sortie contient reellement."""
    return sorted(p.name for p in dossier.glob("*")) if dossier.exists() else []


# --- Les deux tests que l'integration doit passer -------------------------------

def test_produire_ne_part_jamais_sans_confirmation(connecteur, dossier):
    resultat = connecteur.executer("produire", demande=DEMANDE, **DESTINATAIRE)

    assert resultat.statut is not Statut.SUCCES
    assert fichiers(dossier) == [], "un document a ete ecrit sans confirmation"


def test_un_devis_produit_laisse_un_fichier_qui_est_sa_preuve(connecteur, dossier):
    resultat = connecteur.executer_confirmee("produire", demande=DEMANDE, **DESTINATAIRE)

    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve, "un succes sans preuve ne se construit pas"
    ecrit = dossier / resultat.preuve.rsplit("/", 1)[-1]
    assert ecrit.exists(), "la preuve designe un fichier qui n'existe pas"
    assert ecrit.stat().st_size > 0, "le devis produit est vide"
    assert resultat.detail["octets"] == ecrit.stat().st_size


# --- Le destinataire n'est jamais devine -----------------------------------------

def test_sans_destinataire_rien_n_est_produit(connecteur, dossier):
    resultat = connecteur.executer_confirmee("produire", demande=DEMANDE, lieu="Medina")

    assert resultat.statut is Statut.ECHEC
    assert "client" in resultat.message and "objet" in resultat.message, (
        "le refus ne nomme pas ce qui manque")
    assert fichiers(dossier) == [], "un devis sans destinataire a ete ecrit"


# --- Chiffrer ne coute rien -------------------------------------------------------

def test_chiffrer_n_ecrit_aucun_fichier(connecteur, dossier):
    resultat = connecteur.executer("chiffrer", demande=DEMANDE, **DESTINATAIRE)

    assert resultat.statut is Statut.SUCCES, "voir un total demande une confirmation"
    assert fichiers(dossier) == [], "le chiffrage a ecrit sur le disque"


def test_le_total_vient_de_la_grille_de_prix_pas_de_l_appelant(connecteur):
    resultat = connecteur.executer("chiffrer", demande=DEMANDE, prix=1, total=1, **DESTINATAIRE)

    assert resultat.detail["chiffrage"]["total"] == 3298000, (
        "un prix passe par l'appelant a change le total")


def test_un_article_hors_grille_est_nomme_jamais_chiffre_au_juge():
    # Ses ratios reels, mais une grille de prix amputee a un seul article.
    metier = dict(charger_metier())
    metier["prix_materiaux"] = {"Plaque standard BA13": 4500}
    connecteur = DevisConnector(metier=metier)

    chiffrage = connecteur.executer("chiffrer", demande=DEMANDE, **DESTINATAIRE).detail["chiffrage"]

    assert chiffrage["articles_sans_prix"], "des articles absents de la grille ont recu un prix"


# --- Sans dimensions lues, rien ---------------------------------------------------

def test_sans_dimension_lue_rien_n_est_chiffre(connecteur):
    resultat = connecteur.executer("chiffrer", demande="fais-moi un devis", **DESTINATAIRE)

    assert resultat.statut is Statut.ECHEC
    assert "dimension" in resultat.message.lower()


def test_sans_dimension_lue_aucun_document_n_est_produit(connecteur, dossier):
    resultat = connecteur.executer_confirmee("produire", demande="un devis stp", **DESTINATAIRE)

    assert resultat.statut is Statut.ECHEC
    assert fichiers(dossier) == []


def test_lignes_depuis_rend_une_liste_vide_quand_rien_n_est_lu():
    assert lignes_depuis("bonjour", {"prix_materiaux": {}}) == []


# --- La sonde mesure, elle ne suppose pas ------------------------------------------

def test_sans_grille_de_prix_la_sonde_dit_ce_qui_manque():
    sante = DevisConnector(metier={}).sonder()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "unic_plaquiste.yaml" in sante.ce_qui_manque
    assert sante.mesure_le, "une sante sans date n'est pas une mesure"


def test_avec_sa_grille_la_sonde_compte_les_articles(connecteur):
    sante = connecteur.sonder()

    assert sante.etat is EtatSante.OPERATIONNEL
    assert "28" in sante.message, "la sonde n'annonce pas la grille reellement chargee"


# --- Ce que les capacites declarent -------------------------------------------------

def test_seule_la_production_est_declaree_comme_ecriture(connecteur):
    ecritures = {nom for nom, cap in connecteur.capacites().items() if cap.ecriture}

    assert ecritures == {"produire"}
