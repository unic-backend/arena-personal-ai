"""`ClientMcpStdio` : un vrai processus, jamais une exception qui remonte.

Le faux serveur (`faux_serveur_mcp_stdio.py`) est un sous-processus Python
reel — pas un mock du transport lui-meme — pour que ces tests verifient le
protocole (poignee de main, notification glissee, `isError`, timeout,
nettoyage du processus) sans dependre de Node ni du vrai OpenTakeoff.
"""
import sys
from pathlib import Path

import pytest

from core.mcp.stdio_transport import ClientMcpStdio

FAUX_SERVEUR = Path(__file__).parent / "faux_serveur_mcp_stdio.py"
COMMANDE = [sys.executable, str(FAUX_SERVEUR)]
DOSSIER = str(Path(__file__).parent)


class TestPoigneeDeMainEtOutils:
    def test_ouvrir_reussit_et_est_rejouable_sans_effet(self):
        client = ClientMcpStdio(COMMANDE, dossier=DOSSIER)
        try:
            assert client.ouvrir().ok
            assert client.ouvrir().ok  # deuxieme appel : sans effet, pas un second processus
        finally:
            client.fermer()

    def test_outils_rend_la_liste_du_faux_serveur(self):
        with ClientMcpStdio(COMMANDE, dossier=DOSSIER) as client:
            reponse = client.outils()
        assert reponse.ok
        noms = [outil["name"] for outil in reponse.resultat["tools"]]
        assert noms == ["ping", "erreur", "lent"]


class TestAppelDOutil:
    def test_une_notification_glissee_n_est_jamais_prise_pour_la_reponse(self):
        """Le faux serveur emet `notifications/resources/list_changed` juste
        avant sa vraie reponse — exactement ce que le vrai OpenTakeoff fait
        apres `load_plan` (mesure reelle, probe manuel). Un client qui lit la
        premiere ligne recevrait cette notification, pas le resultat."""
        with ClientMcpStdio(COMMANDE, dossier=DOSSIER) as client:
            reponse = client.appeler("ping", {"valeur": 42})
        assert reponse.ok
        assert reponse.donnees() == {"valeur": 42}

    def test_une_erreur_applicative_isError_n_est_pas_un_echec_de_transport(self):
        """Comme sur le vrai serveur (probe manuel, outil inconnu / feuille non
        chargee) : `ok=True`, l'echec est dans `resultat['isError']`."""
        with ClientMcpStdio(COMMANDE, dossier=DOSSIER) as client:
            reponse = client.appeler("erreur", {})
        assert reponse.ok
        assert reponse.resultat["isError"] is True
        assert "erreur applicative simulee" in reponse.contenu_texte

    def test_appeler_sans_session_ouverte_ne_leve_pas(self):
        client = ClientMcpStdio(COMMANDE, dossier=DOSSIER)
        reponse = client.appeler("ping", {})
        assert reponse.ok is False
        assert reponse.raison

    def test_un_delai_depasse_est_un_etat_pas_une_exception(self):
        with ClientMcpStdio(COMMANDE, dossier=DOSSIER, delai=1.0) as client:
            reponse = client.appeler("lent", {})
        assert reponse.ok is False
        assert "delai" in reponse.raison


class TestPanneDeLancement:
    def test_dossier_absent_rend_la_vraie_raison_pas_un_message_generique(self):
        with ClientMcpStdio(COMMANDE, dossier="/aucun/dossier/ici") as client:
            reponse = client.outils()
        assert reponse.ok is False
        assert "No such file or directory" in reponse.raison or "FileNotFoundError" in reponse.raison

    def test_binaire_absent_rend_la_vraie_raison(self):
        with ClientMcpStdio(["binaire-qui-n-existe-pas-ici"], dossier=DOSSIER) as client:
            reponse = client.outils()
        assert reponse.ok is False
        assert "binaire-qui-n-existe-pas-ici" in reponse.raison


class TestNettoyage:
    def test_le_processus_ne_survit_pas_a_la_sortie_du_contexte(self):
        with ClientMcpStdio(COMMANDE, dossier=DOSSIER) as client:
            client.appeler("ping", {})
            processus = client._processus
            assert processus is not None
            assert processus.poll() is None  # vivant, pendant l'usage

        assert processus.poll() is not None, "le processus Node (ici, Python) a survecu au `with`"

    def test_fermer_sans_avoir_ouvert_ne_leve_pas(self):
        client = ClientMcpStdio(COMMANDE, dossier=DOSSIER)
        client.fermer()  # ne doit rien lever


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
