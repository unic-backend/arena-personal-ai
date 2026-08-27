"""Le cadre des connecteurs : cinq choses qu'un connecteur ne peut pas faire.

Les tests sont ecrits contre des doubles, pas contre un service reel : aucun
appel ne sort d'ici. Le double le plus important est `ConnecteurEspion`, qui
note s'il a ete execute — c'est ce qui permet de prouver qu'un refus n'atteint
jamais l'implementation.
"""
from typing import Any, Dict

import pytest
import yaml

from core.actions.journal import JournalDesActions
from core.actions.resultat import ResultatAction, Statut, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.permissions.controle import ControleAcces
from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import PolitiqueDePermissions

# --- Doubles ------------------------------------------------------------------

class ConnecteurEspion(Connecteur):
    """Un connecteur minimal qui note ce qu'on lui a demande de faire."""

    service = "email"
    nom = "espion"

    def __init__(self, *args, sante_rendue: Sante = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.executions: list = []
        self.sondes = 0
        self._sante = sante_rendue or Sante(EtatSante.OPERATIONNEL, "Repond.", mesure_le="2026-08-27T10:00:00+00:00")

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "lire": Capacite("lire", "read", "Lit les messages recents."),
            "envoyer": Capacite("envoyer", "send", "Envoie un message.", ecriture=True),
            "supprimer": Capacite("supprimer", "delete", "Supprime un message.", ecriture=True),
            "etiqueter": Capacite("etiqueter", "label", "Pose une etiquette.",
                                  ecriture=True, quota_par_minute=2),
        }

    def sonder(self) -> Sante:
        self.sondes += 1
        return self._sante

    def authentifier(self) -> bool:
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        self.executions.append((capacite.nom, parametres))
        return succes(capacite.nom, "boite@exemple.sn", "Fait.", f"preuve-{capacite.nom}")


class ConnecteurMuet(Connecteur):
    """Il ne declare aucune capacite. Il ne doit donc rien pouvoir faire."""

    service = "email"
    nom = "muet"

    def capacites(self) -> Dict[str, Capacite]:
        return {}

    def sonder(self) -> Sante:
        return Sante(EtatSante.OPERATIONNEL, "Repond.")

    def authentifier(self) -> bool:
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        raise AssertionError("Un connecteur sans capacite ne doit jamais executer.")


# --- Fixtures -----------------------------------------------------------------

@pytest.fixture
def acces(tmp_path):
    """Politique ouverte en lecture, confirmation a l'envoi, suppression coupee."""
    def _fabriquer(services: dict = None, booleens: dict = None) -> ControleAcces:
        chemin = tmp_path / f"politique-{len(list(tmp_path.iterdir()))}.yaml"
        chemin.write_text(yaml.safe_dump({"services": services or {
            "email": {
                "read": {"decision": "ALLOWED", "risque": "LOW"},
                "label": {"decision": "ALLOWED", "risque": "LOW"},
                "send": {"decision": "CONFIRMATION", "risque": "HIGH"},
                "delete": {"decision": "DENIED", "risque": "HIGH"},
            }
        }}), encoding="utf-8")
        permissions = PermissionManager(config_path=str(tmp_path / "booleens.yaml"))
        permissions.permissions.update({"SEND_MESSAGES": True, "DELETE": True, **(booleens or {})})
        return ControleAcces(permissions=permissions,
                             politique=PolitiqueDePermissions(chemin=chemin))
    return _fabriquer


@pytest.fixture
def journal(tmp_path):
    return JournalDesActions(db_path=str(tmp_path / "journal.db"))


# --- 1. Ce qui n'est pas declare n'existe pas ---------------------------------

def test_un_connecteur_sans_capacite_n_expose_rien(acces):
    connecteur = ConnecteurMuet(acces=acces())

    resultat = connecteur.executer("envoyer", destinataire="x@y.z")

    assert resultat.statut is Statut.NON_IMPLEMENTE
    assert resultat.a_eu_lieu is False


def test_une_capacite_inconnue_n_atteint_pas_l_implementation(acces):
    connecteur = ConnecteurEspion(acces=acces())

    connecteur.executer("capacite_inventee")

    assert connecteur.executions == []


def test_une_capacite_inconnue_dit_laquelle(acces):
    resultat = ConnecteurEspion(acces=acces()).executer("capacite_inventee")

    assert "capacite_inventee" in resultat.message
    assert "Rien n'a ete tente" in resultat.message


def test_l_inventaire_ne_montre_que_les_capacites_declarees(acces):
    assert ConnecteurMuet(acces=acces()).to_dict()["capacites"] == []
    assert len(ConnecteurEspion(acces=acces()).to_dict()["capacites"]) == 4


# --- 2. La permission passe avant tout ----------------------------------------

def test_une_action_refusee_n_atteint_pas_l_implementation(acces):
    connecteur = ConnecteurEspion(acces=acces())

    resultat = connecteur.executer("supprimer", identifiant="42")

    assert resultat.statut is Statut.REFUSE
    assert connecteur.executions == []


def test_une_action_refusee_ne_sonde_meme_pas_le_service(acces):
    """Un refus ne doit pas reveler si le service est joignable."""
    connecteur = ConnecteurEspion(acces=acces())

    connecteur.executer("supprimer")

    assert connecteur.sondes == 0


def test_un_refus_dit_quelle_regle_a_tranche(acces):
    resultat = ConnecteurEspion(acces=acces()).executer("supprimer")

    assert "service" in resultat.message


def test_un_coupe_circuit_eteint_refuse_avant_la_sonde(acces):
    connecteur = ConnecteurEspion(acces=acces(booleens={"SEND_MESSAGES": False}))

    resultat = connecteur.executer("envoyer")

    assert resultat.statut is Statut.REFUSE
    assert "coupe-circuit:SEND_MESSAGES" in resultat.message
    assert connecteur.sondes == 0


def test_une_action_a_confirmer_n_est_pas_executee(acces):
    connecteur = ConnecteurEspion(acces=acces())

    resultat = connecteur.executer("envoyer", destinataire="client@exemple.sn")

    assert resultat.statut is Statut.A_CONFIRMER
    assert resultat.a_eu_lieu is False
    assert connecteur.executions == []


def test_une_action_a_confirmer_annonce_son_risque(acces):
    resultat = ConnecteurEspion(acces=acces()).executer("envoyer")

    assert "HIGH" in resultat.message
    assert "Rien n'est parti" in resultat.message


def test_une_action_autorisee_est_bien_executee(acces):
    connecteur = ConnecteurEspion(acces=acces())

    resultat = connecteur.executer("lire", limite=10)

    assert resultat.statut is Statut.SUCCES
    assert connecteur.executions == [("lire", {"limite": 10})]


# --- 3. La sante est mesuree, jamais supposee ---------------------------------

def test_un_connecteur_non_configure_ne_tente_rien(acces):
    connecteur = ConnecteurEspion(
        acces=acces(),
        sante_rendue=Sante(EtatSante.NON_CONFIGURE, ce_qui_manque="un jeton OAuth"),
    )

    resultat = connecteur.executer("lire")

    assert resultat.statut is Statut.NON_CONFIGURE
    assert "un jeton OAuth" in resultat.message
    assert connecteur.executions == []


def test_un_connecteur_en_panne_echoue_sans_inventer(acces):
    connecteur = ConnecteurEspion(
        acces=acces(), sante_rendue=Sante(EtatSante.EN_PANNE, message="502 du serveur"),
    )

    resultat = connecteur.executer("lire")

    assert resultat.statut is Statut.ECHEC
    assert "502" in resultat.message
    assert connecteur.executions == []


def test_un_etat_inconnu_ne_vaut_pas_operationnel(acces):
    connecteur = ConnecteurEspion(acces=acces(), sante_rendue=Sante(EtatSante.INCONNU))

    assert connecteur.executer("lire").a_eu_lieu is False


def test_une_sonde_qui_leve_rend_en_panne_sans_remonter(acces):
    class Casse(ConnecteurEspion):
        def sonder(self):
            raise RuntimeError("socket ferme")

    sante = Casse(acces=acces()).sante()

    assert sante.etat is EtatSante.EN_PANNE
    assert "socket ferme" in sante.message
    assert sante.mesure_le is not None


def test_une_sonde_qui_rend_n_importe_quoi_donne_inconnu(acces):
    class Bavarde(ConnecteurEspion):
        def sonder(self):
            return "tout va bien"

    assert Bavarde(acces=acces()).sante().etat is EtatSante.INCONNU


def test_un_connecteur_casse_ne_fait_pas_tomber_l_inventaire(acces):
    class Casse(ConnecteurEspion):
        def sonder(self):
            raise RuntimeError("socket ferme")

    assert Casse(acces=acces()).to_dict()["sante"]["etat"] == "FAILING"


def test_une_sante_sans_mesure_n_est_pas_utilisable():
    assert Sante(EtatSante.INCONNU).utilisable is False
    assert Sante(EtatSante.OPERATIONNEL).utilisable is True


# --- 4. Une implementation ne peut pas fabriquer un succes --------------------

def test_une_implementation_qui_leve_devient_un_echec(acces):
    class Explosive(ConnecteurEspion):
        def _executer(self, capacite, **parametres):
            raise ConnectionError("connexion perdue")

    resultat = Explosive(acces=acces()).executer("lire")

    assert resultat.statut is Statut.ECHEC
    assert "connexion perdue" in resultat.message


def test_une_implementation_qui_rend_un_dictionnaire_devient_un_echec(acces):
    class Bavarde(ConnecteurEspion):
        def _executer(self, capacite, **parametres):
            return {"status": "success", "message": "publie !"}

    resultat = Bavarde(acces=acces()).executer("lire")

    assert resultat.statut is Statut.ECHEC
    assert resultat.a_eu_lieu is False


def test_un_echec_de_l_implementation_est_rendu_tel_quel(acces):
    class Honnete(ConnecteurEspion):
        def _executer(self, capacite, **parametres):
            return echec(capacite.nom, "boite", "quota du fournisseur atteint")

    resultat = Honnete(acces=acces()).executer("lire")

    assert resultat.statut is Statut.ECHEC
    assert "quota du fournisseur" in resultat.message


# --- 5. Les quotas ------------------------------------------------------------

def test_le_quota_declare_est_applique(acces):
    connecteur = ConnecteurEspion(acces=acces())

    premiers = [connecteur.executer("etiqueter").statut for _ in range(2)]
    troisieme = connecteur.executer("etiqueter")

    assert premiers == [Statut.SUCCES, Statut.SUCCES]
    assert troisieme.statut is Statut.ECHEC
    assert "Quota atteint" in troisieme.message


def test_une_capacite_sans_quota_n_est_pas_limitee(acces):
    connecteur = ConnecteurEspion(acces=acces())

    assert all(connecteur.executer("lire").statut is Statut.SUCCES for _ in range(20))


def test_le_quota_ne_compte_pas_les_actions_refusees(acces):
    """Un refus n'a rien consomme chez le fournisseur."""
    connecteur = ConnecteurEspion(acces=acces())
    for _ in range(5):
        connecteur.executer("supprimer")

    assert connecteur.executer("etiqueter").statut is Statut.SUCCES


# --- Le journal ---------------------------------------------------------------

@pytest.mark.parametrize("capacite,attendu", [
    ("lire", "SUCCESS"), ("envoyer", "NEEDS_CONFIRMATION"),
    ("supprimer", "DENIED"), ("inconnue", "NOT_IMPLEMENTED"),
])
def test_chaque_issue_laisse_une_trace(acces, journal, capacite, attendu):
    ConnecteurEspion(acces=acces(), journal=journal).executer(capacite)

    assert journal.dernieres()[0].resultat == attendu


def test_le_journal_note_le_niveau_de_permission(acces, journal):
    ConnecteurEspion(acces=acces(), journal=journal).executer("envoyer")

    assert journal.dernieres()[0].niveau_permission == "CONFIRMATION"


def test_sans_journal_le_connecteur_fonctionne(acces):
    assert ConnecteurEspion(acces=acces(), journal=None).executer("lire").a_eu_lieu is True


def test_un_journal_en_panne_n_empeche_pas_l_action(acces, journal, monkeypatch):
    monkeypatch.setattr(journal, "enregistrer", lambda action: False)

    assert ConnecteurEspion(acces=acces(), journal=journal).executer("lire").a_eu_lieu is True


# --- Aucun identifiant ne sort -------------------------------------------------

def test_l_inventaire_expose_des_capacites_jamais_des_secrets(acces):
    class AvecJeton(ConnecteurEspion):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._jeton = "ya29.SECRET-ABSOLU"

    corps = AvecJeton(acces=acces()).to_dict()

    assert "ya29.SECRET-ABSOLU" not in str(corps)
    assert {c["nom"] for c in corps["capacites"]} == {"lire", "envoyer", "supprimer", "etiqueter"}


def test_un_secret_passe_en_parametre_est_masque_dans_le_journal(acces, journal):
    ConnecteurEspion(acces=acces(), journal=journal).executer("lire", access_token="ya29.SECRET")

    assert "ya29.SECRET" not in journal.db_path.read_bytes().decode("utf-8", "ignore")


# --- La declaration d'une capacite ---------------------------------------------

def test_une_capacite_distingue_son_nom_et_son_action():
    capacite = Capacite("publish_video", "publish", "Publie une video.", ecriture=True)

    assert capacite.nom != capacite.action
    assert capacite.to_dict()["action"] == "publish"


def test_une_capacite_dit_si_elle_ecrit_dehors():
    assert Capacite("lire", "read", "…").ecriture is False
    assert Capacite("envoyer", "send", "…", ecriture=True).ecriture is True
