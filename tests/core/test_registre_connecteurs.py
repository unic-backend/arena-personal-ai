"""Le registre : paresseux, et tolerant a un connecteur qui tombe.

Le test qui compte le plus est
`test_un_connecteur_qui_explose_a_la_construction_ne_fait_tomber_personne` :
`runtime.py` construit ses agents a l'import, et un connecteur depend d'un
service exterieur — donc il tombera. Le jour ou il tombe, le serveur doit
demarrer quand meme.
"""
from typing import Any, Dict

import pytest

from core.actions.resultat import ResultatAction, Statut, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.connectors.registre import RegistreConnecteurs


class ConnecteurSimple(Connecteur):
    """Connecteur minimal, en bonne sante, avec une capacite autorisee."""

    service = "email"
    nom = "simple"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executions = 0

    def capacites(self) -> Dict[str, Capacite]:
        return {"lire": Capacite("lire", "read", "Lit les messages.")}

    def sonder(self) -> Sante:
        return Sante(EtatSante.OPERATIONNEL, "Repond.", mesure_le="2026-08-27T10:00:00+00:00")

    def authentifier(self) -> bool:
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        self.executions += 1
        return succes(capacite.nom, "boite", "Fait.", "preuve-1")


@pytest.fixture
def registre():
    return RegistreConnecteurs()


# --- Paresse ------------------------------------------------------------------

def test_declarer_ne_construit_rien(registre):
    """C'est tout l'interet : dix-sept objets construits a l'import, c'est ce
    qu'on evite."""
    construits = []
    registre.declarer("simple", lambda: construits.append(1) or ConnecteurSimple())

    assert construits == []
    assert registre.est_declare("simple") is True


def test_le_connecteur_naît_au_premier_usage(registre):
    constructions = []
    registre.declarer("simple", lambda: (constructions.append(1), ConnecteurSimple())[1])

    registre.obtenir("simple")

    assert len(constructions) == 1


def test_il_n_est_construit_qu_une_fois(registre):
    constructions = []
    registre.declarer("simple", lambda: (constructions.append(1), ConnecteurSimple())[1])

    premier = registre.obtenir("simple")
    second = registre.obtenir("simple")

    assert premier is second
    assert len(constructions) == 1


# --- Un connecteur casse se degrade seul --------------------------------------

def test_un_connecteur_qui_explose_a_la_construction_ne_fait_tomber_personne(registre):
    def fabrique_cassee():
        raise RuntimeError("identifiants illisibles")

    registre.declarer("casse", fabrique_cassee)
    registre.declarer("simple", ConnecteurSimple)

    assert registre.obtenir("casse") is None
    assert registre.obtenir("simple") is not None
    assert registre.executer("simple", "lire").statut is Statut.SUCCES


def test_une_construction_cassee_n_est_pas_retentee(registre):
    tentatives = []

    def fabrique_cassee():
        tentatives.append(1)
        raise RuntimeError("toujours la meme panne")

    registre.declarer("casse", fabrique_cassee)
    for _ in range(5):
        registre.obtenir("casse")

    assert len(tentatives) == 1


def test_un_connecteur_casse_rend_une_sante_qui_porte_sa_cause(registre):
    registre.declarer("casse", lambda: (_ for _ in ()).throw(RuntimeError("jeton absent")))

    sante = registre.sante("casse")

    assert sante.etat is EtatSante.EN_PANNE
    assert "jeton absent" in sante.message


def test_une_fabrique_qui_rend_autre_chose_qu_un_connecteur_est_cassee(registre):
    registre.declarer("faux", lambda: {"nom": "je ressemble a un connecteur"})

    assert registre.obtenir("faux") is None
    assert registre.sante("faux").etat is EtatSante.EN_PANNE


def test_redeclarer_oublie_la_panne(registre):
    """Apres correction de la configuration, le connecteur doit pouvoir renaitre."""
    registre.declarer("x", lambda: (_ for _ in ()).throw(RuntimeError("panne")))
    assert registre.obtenir("x") is None

    registre.declarer("x", ConnecteurSimple)

    assert registre.obtenir("x") is not None


# --- Un nom inconnu est une reponse, pas une exception ------------------------

def test_un_nom_inconnu_ne_leve_pas(registre):
    assert registre.obtenir("jamais_declare") is None


def test_executer_un_nom_inconnu_rend_non_implemente(registre):
    resultat = registre.executer("jamais_declare", "lire")

    assert resultat.statut is Statut.NON_IMPLEMENTE
    assert "non declare" in resultat.message
    assert resultat.a_eu_lieu is False


def test_executer_un_connecteur_casse_dit_pourquoi(registre):
    registre.declarer("casse", lambda: (_ for _ in ()).throw(RuntimeError("jeton absent")))

    resultat = registre.executer("casse", "lire")

    assert resultat.statut is Statut.NON_IMPLEMENTE
    assert "hors service" in resultat.message
    assert "jeton absent" in resultat.message


def test_la_sante_d_un_nom_inconnu_est_inconnue(registre):
    assert registre.sante("jamais_declare").etat is EtatSante.INCONNU


# --- L'inventaire ne leve jamais ----------------------------------------------

def test_l_inventaire_d_un_registre_vide_est_vide(registre):
    assert registre.inventaire() == []


def test_l_inventaire_liste_les_connecteurs_sains(registre):
    registre.declarer("simple", ConnecteurSimple)

    inventaire = registre.inventaire()

    assert len(inventaire) == 1
    assert inventaire[0]["nom"] == "simple"
    assert inventaire[0]["sante"]["etat"] == "OPERATIONAL"
    assert [c["nom"] for c in inventaire[0]["capacites"]] == ["lire"]


def test_l_inventaire_montre_un_connecteur_casse_au_lieu_de_l_omettre(registre):
    """Un connecteur absent de la liste passe inapercu. Un connecteur en panne,
    non."""
    registre.declarer("casse", lambda: (_ for _ in ()).throw(RuntimeError("panne")))
    registre.declarer("simple", ConnecteurSimple)

    inventaire = {c["nom"]: c for c in registre.inventaire()}

    assert set(inventaire) == {"casse", "simple"}
    assert inventaire["casse"]["sante"]["etat"] == "FAILING"
    assert inventaire["casse"]["capacites"] == []


def test_l_inventaire_survit_a_un_connecteur_dont_la_description_leve(registre):
    class Bavarde(ConnecteurSimple):
        def capacites(self):
            raise RuntimeError("capacites illisibles")

    registre.declarer("bavarde", Bavarde)
    registre.declarer("simple", ConnecteurSimple)

    inventaire = {c["nom"]: c for c in registre.inventaire()}

    assert inventaire["bavarde"]["sante"]["etat"] == "FAILING"
    assert inventaire["simple"]["sante"]["etat"] == "OPERATIONAL"


def test_les_noms_incluent_les_connecteurs_casses(registre):
    registre.declarer("casse", lambda: (_ for _ in ()).throw(RuntimeError("panne")))
    registre.declarer("simple", ConnecteurSimple)

    assert registre.noms() == ["casse", "simple"]


# --- Aiguillage ---------------------------------------------------------------

def test_executer_route_vers_le_bon_connecteur(registre):
    registre.declarer("simple", ConnecteurSimple)

    resultat = registre.executer("simple", "lire", limite=5)

    assert resultat.statut is Statut.SUCCES
    assert registre.obtenir("simple").executions == 1


def test_executer_une_capacite_inconnue_passe_par_le_connecteur(registre):
    """C'est le connecteur qui refuse, avec son propre message."""
    registre.declarer("simple", ConnecteurSimple)

    resultat = registre.executer("simple", "capacite_inventee")

    assert resultat.statut is Statut.NON_IMPLEMENTE
    assert "capacite_inventee" in resultat.message


# --- La plateforme ------------------------------------------------------------

def test_la_plateforme_declare_tiktok_sans_le_construire_a_l_import():
    from apps.backend import runtime

    assert "tiktok" in runtime.registre.noms()


def test_la_plateforme_rend_un_inventaire_lisible():
    from apps.backend import runtime

    inventaire = {c["nom"]: c for c in runtime.registre.inventaire()}

    assert inventaire["tiktok"]["sante"]["etat"] in {"NOT_CONFIGURED", "UNKNOWN"}
    assert [c["nom"] for c in inventaire["tiktok"]["capacites"]] == ["publish_video"]
