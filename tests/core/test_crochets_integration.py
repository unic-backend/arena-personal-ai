"""Preuve bout en bout : un vrai connecteur, cable exactement comme
`apps/backend/runtime.py` le fait, avec le disjoncteur comme premier
consommateur reel des crochets — pas un import qu'on verifie, un
comportement qu'on observe.

Le service est `email` / action `read` : `ALLOWED` dans la vraie politique
(`config/permissions_services.yaml`), donc aucune politique de test n'est
necessaire pour atteindre `_executer()`.
"""
from typing import Any, Dict

from core.actions.resultat import ResultatAction, Statut, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.execution.disjoncteur import Disjoncteur
from core.execution.hooks import RegistreDeCrochets


class ConnecteurInstable(Connecteur):
    """Reussit ou echoue sur commande — pour observer le disjoncteur reagir
    a un VRAI enchainement d'echecs, pas a un double qui ne fait que passer."""

    service = "email"
    nom = "instable"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.appels_reels = 0
        self.echouer = False

    def capacites(self) -> Dict[str, Capacite]:
        return {"lire": Capacite("lire", "read", "Lit.", ecriture=False)}

    def sonder(self) -> Sante:
        return Sante(EtatSante.OPERATIONNEL, "Repond.")

    def authentifier(self) -> bool:
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        self.appels_reels += 1
        if self.echouer:
            return echec(capacite.nom, self.nom, "service en panne")
        return succes(capacite.nom, self.nom, "ok", "preuve")


def _cablage(seuil: int = 3) -> tuple:
    """Le meme cablage que runtime.py : un registre, un disjoncteur dessus."""
    crochets = RegistreDeCrochets()
    disjoncteur = Disjoncteur(seuil=seuil, repos_secondes=60.0)
    crochets.avant(disjoncteur.avant_execution)
    crochets.apres(disjoncteur.apres_execution)
    return crochets, disjoncteur


class TestSansCrochets:
    def test_le_comportement_est_identique_a_avant_ce_module(self):
        """Un connecteur sans `crochets` (le defaut) se comporte exactement
        comme avant l'existence de hooks.py — aucune regression."""
        connecteur = ConnecteurInstable()

        resultat = connecteur.executer("lire")

        assert resultat.statut is Statut.SUCCES
        assert connecteur.appels_reels == 1


class TestLeDisjoncteurCoupeApresDesEchecsReels:
    def test_le_service_tourne_reellement_avant_ouverture(self):
        crochets, _ = _cablage(seuil=3)
        connecteur = ConnecteurInstable(crochets=crochets)
        connecteur.echouer = True

        for _ in range(3):
            resultat = connecteur.executer("lire")
            assert resultat.statut is Statut.ECHEC

        assert connecteur.appels_reels == 3, "les 3 echecs doivent avoir reellement appele le service"

    def test_l_appel_suivant_ne_touche_plus_le_service(self):
        """La preuve du 'court-circuit' : `_executer` n'est PAS rappele une
        4e fois — le connecteur repond sans jamais retourner vers le service
        tombe."""
        crochets, _ = _cablage(seuil=3)
        connecteur = ConnecteurInstable(crochets=crochets)
        connecteur.echouer = True
        for _ in range(3):
            connecteur.executer("lire")

        resultat = connecteur.executer("lire")

        assert resultat.statut is Statut.ECHEC
        assert "Disjoncteur ouvert" in resultat.message
        assert connecteur.appels_reels == 3, "le 4e appel n'a pas du atteindre _executer()"

    def test_un_service_qui_se_retablit_referme_le_disjoncteur(self):
        crochets, _ = _cablage(seuil=3)
        connecteur = ConnecteurInstable(crochets=crochets)
        connecteur.echouer = True
        for _ in range(3):
            connecteur.executer("lire")
        assert "Disjoncteur ouvert" in connecteur.executer("lire").message

        # Le proprietaire relance le service ; le prochain vrai essai doit
        # pouvoir se faire, pas rester coince derriere un vieux compteur.
        import time as temps_module

        crochets2, disjoncteur2 = _cablage(seuil=3)
        disjoncteur2._etat_de("instable", "lire").ouvert_jusqua = temps_module.monotonic() - 1
        connecteur2 = ConnecteurInstable(crochets=crochets2)
        connecteur2.echouer = False

        resultat = connecteur2.executer("lire")

        assert resultat.statut is Statut.SUCCES
        assert connecteur2.appels_reels == 1

    def test_deux_connecteurs_partageant_le_meme_registre_restent_independants(self):
        """Le partage du meme `RegistreDeCrochets` (comme dans runtime.py, un
        seul objet pour tous les connecteurs) ne doit pas melanger leurs
        compteurs : la cle porte le service, pas seulement la capacite."""
        crochets, _ = _cablage(seuil=2)

        class AutreConnecteur(ConnecteurInstable):
            service = "calendar"
            nom = "autre"

        instable = ConnecteurInstable(crochets=crochets)
        instable.echouer = True
        autre = AutreConnecteur(crochets=crochets)

        for _ in range(2):
            instable.executer("lire")

        assert "Disjoncteur ouvert" in instable.executer("lire").message
        assert autre.executer("lire").statut is Statut.SUCCES


class TestJournalInchange:
    def test_un_appel_court_circuite_est_quand_meme_journalise(self, tmp_path):
        """Le disjoncteur ne doit pas faire disparaitre la trace : un appel
        refuse par lui reste une action journalisee, comme tout le reste."""
        from core.actions.journal import JournalDesActions

        crochets, _ = _cablage(seuil=1)
        journal = JournalDesActions(db_path=str(tmp_path / "journal.db"))
        connecteur = ConnecteurInstable(crochets=crochets, journal=journal)
        connecteur.echouer = True
        connecteur.executer("lire")  # ouvre le disjoncteur (seuil=1)

        connecteur.executer("lire")  # court-circuite

        recentes = journal.dernieres(limite=5)
        assert len(recentes) == 2, "les deux tentatives (reelle et court-circuitee) doivent etre journalisees"
