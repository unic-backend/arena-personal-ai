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
    """Une panne de lancement doit dire CE QUI n'a pas démarré.

    Mesuré le 30/08/2026 sur la machine du propriétaire (Windows) : ces deux
    tests attendaient le message d'erreur **de Linux**. Windows répond
    « [WinError 2] Le fichier spécifié est introuvable » — sans nommer le
    fichier — et « [WinError 267] Nom de répertoire invalide ». Les tests
    échouaient chez lui et passaient en CI : la garantie n'était vérifiée que
    sur un seul système.

    La correction n'est pas d'affaiblir l'assertion. C'est le **connecteur**
    qui porte maintenant la commande et le dossier dans sa raison, pour que la
    promesse tienne là où le système ne la tient pas.
    """

    def test_dossier_absent_rend_la_vraie_raison_pas_un_message_generique(self):
        with ClientMcpStdio(COMMANDE, dossier="/aucun/dossier/ici") as client:
            reponse = client.outils()
        assert reponse.ok is False
        assert "/aucun/dossier/ici" in reponse.raison, (
            "la raison ne nomme pas le dossier introuvable")
        assert "Error" in reponse.raison, "le type de la panne manque"

    def test_binaire_absent_rend_la_vraie_raison(self):
        with ClientMcpStdio(["binaire-qui-n-existe-pas-ici"], dossier=DOSSIER) as client:
            reponse = client.outils()
        assert reponse.ok is False
        assert "binaire-qui-n-existe-pas-ici" in reponse.raison, (
            "la raison ne nomme pas le programme qui n'a pas démarré")


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


class TestLectureMultiplateforme:
    """La lecture du flux doit marcher aussi sous Windows.

    Mesure du 29/08/2026 sur la machine du proprietaire : la premiere version
    attendait sur `selectors.DefaultSelector().select()` applique au
    descripteur du pipe `stdout` du sous-processus. Sous Windows, `select()`
    n'accepte que des sockets — jamais un pipe — d'ou `OSError: [WinError
    10038]` a **chaque** appel MCP. OpenTakeoff etait inutilisable la-bas,
    alors qu'il tournait de bout en bout ici.

    Le test qui compte est structurel, et il l'est pour une raison : sous
    Linux, `select()` sur un pipe **fonctionne**. Aucun test de comportement
    lance sur cette machine ne peut voir la panne. Seule l'absence de
    `select()` dans le chemin de lecture se verifie des deux cotes.
    """

    SOURCE = Path(__file__).resolve().parents[2] / "core" / "mcp" / "stdio_transport.py"

    def test_le_chemin_de_lecture_n_appelle_aucun_select(self):
        code = self.SOURCE.read_text(encoding="utf-8")
        # La docstring du module raconte la panne : on ne lit que le code.
        sans_entete = code.split('"""', 2)[-1]

        assert "selectors" not in sans_entete, (
            "`selectors` est revenu dans le chemin de lecture. Sous Windows, "
            "select() sur le pipe d'un sous-processus leve WinError 10038 a "
            "chaque appel MCP — voir la regle 4 du module.")
        assert ".select(" not in sans_entete

    def test_le_thread_lecteur_ne_survit_pas_a_la_fermeture(self):
        client = ClientMcpStdio(COMMANDE, dossier=DOSSIER)
        client.ouvrir()
        lecteur = client._lecteur
        assert lecteur is not None and lecteur.is_alive()

        client.fermer()

        assert not lecteur.is_alive(), "un thread lecteur survit a son processus"
        assert client._lecteur is None

    def test_une_session_rouverte_ne_traine_pas_le_flux_de_la_precedente(self):
        """Un morceau non consomme de la session d'avant ferait deraper la suivante."""
        client = ClientMcpStdio(COMMANDE, dossier=DOSSIER)
        client.ouvrir()
        client._tampon = b'{"jsonrpc": "2.0", "id": "restant"'  # ligne incomplete
        client.fermer()

        try:
            assert client.ouvrir().ok
            assert client._tampon == b"", "le tampon de la session precedente a survecu"
            assert client.outils().ok
        finally:
            client.fermer()

    def test_un_processus_mort_rend_une_raison_sans_attendre_le_delai(self):
        """Le fil se ferme, le thread pousse la fin du flux : pas d'attente inutile."""
        import time as _time

        client = ClientMcpStdio(COMMANDE, dossier=DOSSIER, delai=30.0)
        client.ouvrir()
        client._processus.kill()
        client._processus.wait(timeout=5)

        debut = _time.monotonic()
        reponse = client.outils()
        ecoule = _time.monotonic() - debut
        client.fermer()

        assert not reponse.ok
        assert reponse.raison, "une panne sans raison n'est pas un etat"
        assert ecoule < 10, f"a attendu {ecoule:.1f}s alors que le processus etait mort"
