"""Le connecteur Formbricks reste-t-il un appel HTTP, jamais du code copie ?

Contexte (DEC-0052) : Formbricks (formbricks/formbricks) a un coeur AGPLv3 —
verifie directement dans son LICENSE. Aucune ligne de son code n'est ici :
ce connecteur appelle son API REST management (documentee, verifiee dans le
code source amont) par HTTP, comme VoiceStudio (AGPL, core/connectors/
audio_voix.py). Aucune instance reelle n'existe pour ce proprietaire — les
tests simulent une instance via un faux client HTTP, jamais un vrai serveur.
"""
import pytest

from core.actions.resultat import Statut
from core.connectors.base import ControleAcces, EtatSante
from core.connectors.formbricks import ConnecteurFormbricks
from core.permissions.permission_manager import PermissionManager


@pytest.fixture
def connecteur_avec_publish_active(tmp_path):
    """`PUBLISH` est eteint par defaut dans le vrai `config/permissions.yaml` —
    ces tests verifient le CHEMIN d'ecriture, pas ce coupe-circuit precis
    (deja verifie separement, `TestLeCoupeCircuitPublish`)."""
    permissions = PermissionManager(config_path=str(tmp_path / "booleens.yaml"))
    permissions.permissions.update({"PUBLISH": True})
    return ConnecteurFormbricks(acces=ControleAcces(permissions=permissions))


@pytest.fixture(autouse=True)
def _configuration_complete(monkeypatch):
    monkeypatch.setenv("FORMBRICKS_BASE_URL", "http://192.168.1.50:3000")
    monkeypatch.setenv("FORMBRICKS_API_KEY", "cle-de-test")
    monkeypatch.setenv("FORMBRICKS_WORKSPACE_ID", "workspace-test")


class FausseReponse:
    def __init__(self, status_code=200, donnees=None, texte=""):
        self.status_code = status_code
        self._donnees = donnees or {}
        self.text = texte or str(donnees)

    def json(self):
        return self._donnees


class FauxClient:
    """Un instantane figé de ce qu'une vraie instance Formbricks rendrait —
    jamais un serveur reel, absent pour ce proprietaire."""

    reponses_get: dict = {}
    reponses_post: dict = {}
    appels: list = []

    def __init__(self, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, headers=None, params=None):
        FauxClient.appels.append(("GET", url, headers, params))
        for suffixe, reponse in FauxClient.reponses_get.items():
            if url.endswith(suffixe):
                return reponse
        return FausseReponse(404, {"error": "introuvable"})

    def post(self, url, headers=None, json=None):
        FauxClient.appels.append(("POST", url, headers, json))
        for suffixe, reponse in FauxClient.reponses_post.items():
            if url.endswith(suffixe):
                return reponse
        return FausseReponse(404, {"error": "introuvable"})


@pytest.fixture(autouse=True)
def _reinitialiser_faux_client(monkeypatch):
    import core.connectors.formbricks as module
    # `_conduire()` sonde avant d'executer : une instance en bonne sante par
    # defaut, que chaque test de sonde peut ecraser explicitement.
    FauxClient.reponses_get = {"/api/v1/management/me": FausseReponse(200, {"id": "u1"})}
    FauxClient.reponses_post = {}
    FauxClient.appels = []
    monkeypatch.setattr(module.httpx, "Client", FauxClient)


class TestConfiguration:
    def test_sans_base_url_non_configure(self, monkeypatch):
        monkeypatch.delenv("FORMBRICKS_BASE_URL", raising=False)
        sante = ConnecteurFormbricks().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "FORMBRICKS_BASE_URL" in sante.ce_qui_manque

    def test_sans_cle_api_non_configure(self, monkeypatch):
        monkeypatch.delenv("FORMBRICKS_API_KEY", raising=False)
        sante = ConnecteurFormbricks().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE

    def test_sans_workspace_id_non_configure(self, monkeypatch):
        monkeypatch.delenv("FORMBRICKS_WORKSPACE_ID", raising=False)
        sante = ConnecteurFormbricks().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE

    def test_aucune_url_par_defaut_n_est_devinee(self, monkeypatch):
        """Jamais l'URL cloud de Formbricks devinee a la place d'une
        instance auto-hebergee non configuree (DEC-0002)."""
        monkeypatch.delenv("FORMBRICKS_BASE_URL", raising=False)
        resultat = ConnecteurFormbricks().executer_confirmee(
            "lister")
        assert resultat.statut is Statut.NON_CONFIGURE
        assert FauxClient.appels == []


class TestSonde:
    def test_instance_joignable_operationnel(self):
        FauxClient.reponses_get = {"/api/v1/management/me": FausseReponse(200, {"id": "u1"})}
        sante = ConnecteurFormbricks().sonder()
        assert sante.etat is EtatSante.OPERATIONNEL

    def test_cle_refusee_non_configure(self):
        FauxClient.reponses_get = {"/api/v1/management/me": FausseReponse(401)}
        sante = ConnecteurFormbricks().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "cle API" in sante.ce_qui_manque

    def test_instance_injoignable_non_configure(self, monkeypatch):
        import httpx

        import core.connectors.formbricks as module

        class ClientQuiEchoue:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, *a, **kw):
                raise httpx.ConnectError("refuse")

        monkeypatch.setattr(module.httpx, "Client", ClientQuiEchoue)
        sante = ConnecteurFormbricks().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE


class TestCreer:
    def test_cree_un_sondage_reel(self, connecteur_avec_publish_active):
        FauxClient.reponses_post = {
            "/api/v1/management/surveys": FausseReponse(201, {"data": {"id": "srv_123"}}),
        }
        resultat = connecteur_avec_publish_active.executer_confirmee(
            "creer", titre="Satisfaction chantier", question="Comment s'est passe le chantier ?")
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["survey_id"] == "srv_123"

        appels_post = [a for a in FauxClient.appels if a[0] == "POST"]
        assert len(appels_post) == 1
        _, url, entetes, corps = appels_post[0]
        assert entetes["x-api-key"] == "cle-de-test"
        assert corps["workspaceId"] == "workspace-test"
        assert corps["questions"][0]["type"] == "openText"
        assert corps["questions"][0]["headline"]["default"] == "Comment s'est passe le chantier ?"

    def test_sans_titre_est_un_echec(self, connecteur_avec_publish_active):
        resultat = connecteur_avec_publish_active.executer_confirmee(
            "creer", titre="", question="une question")
        assert resultat.statut is Statut.ECHEC
        # La sonde de sante (GET /me) tourne quand meme avant l'execution ;
        # ce qui compte ici, c'est qu'aucune ECRITURE n'ait ete tentee.
        assert [a for a in FauxClient.appels if a[0] == "POST"] == []

    def test_sans_question_est_un_echec(self, connecteur_avec_publish_active):
        resultat = connecteur_avec_publish_active.executer_confirmee(
            "creer", titre="un titre", question="")
        assert resultat.statut is Statut.ECHEC

    def test_instance_refuse_la_creation(self, connecteur_avec_publish_active):
        FauxClient.reponses_post = {
            "/api/v1/management/surveys": FausseReponse(400, texte="workspaceId invalide"),
        }
        resultat = connecteur_avec_publish_active.executer_confirmee(
            "creer", titre="t", question="q")
        assert resultat.statut is Statut.ECHEC
        assert "invalide" in resultat.message


class TestLister:
    def test_liste_reelle(self):
        FauxClient.reponses_get.update({
            "/api/v1/management/surveys": FausseReponse(
                200, {"data": [{"id": "s1"}, {"id": "s2"}]}),
        })
        resultat = ConnecteurFormbricks().executer_confirmee("lister")
        assert resultat.statut is Statut.SUCCES
        assert len(resultat.detail["sondages"]) == 2


class TestObtenir:
    def test_sondage_trouve(self):
        FauxClient.reponses_get.update({
            "/api/v1/management/surveys/srv_1": FausseReponse(200, {"data": {"id": "srv_1"}}),
        })
        resultat = ConnecteurFormbricks().executer_confirmee("obtenir", survey_id="srv_1")
        assert resultat.statut is Statut.SUCCES

    def test_sans_survey_id_est_un_echec(self):
        resultat = ConnecteurFormbricks().executer_confirmee("obtenir", survey_id="")
        assert resultat.statut is Statut.ECHEC

    def test_sondage_introuvable(self):
        FauxClient.reponses_get.update({
            "/api/v1/management/surveys/srv_x": FausseReponse(404),
        })
        resultat = ConnecteurFormbricks().executer_confirmee("obtenir", survey_id="srv_x")
        assert resultat.statut is Statut.ECHEC
        assert "introuvable" in resultat.message


class TestReponsesEtAnalyse:
    def test_reponses_brutes_jamais_ecrites_dans_la_memoire(self):
        """Le connecteur ne connait meme pas la memoire personnelle : aucun
        import, aucun appel. Les donnees repartent vers l'appelant, point."""
        import core.connectors.formbricks as module
        assert "memory" not in module.__file__
        assert not any("memoire" in ligne or "memory" in ligne
                       for ligne in open(module.__file__, encoding="utf-8")
                       if "import" in ligne)

    def test_reponses_reelles(self):
        FauxClient.reponses_get.update({
            "/api/v1/management/responses": FausseReponse(
                200, {"data": [{"id": "r1", "finished": True}, {"id": "r2", "finished": False}]}),
        })
        resultat = ConnecteurFormbricks().executer_confirmee("reponses", survey_id="srv_1")
        assert resultat.statut is Statut.SUCCES
        assert len(resultat.detail["reponses"]) == 2

    def test_analyse_compte_sur_les_vraies_reponses(self):
        FauxClient.reponses_get.update({
            "/api/v1/management/responses": FausseReponse(
                200, {"data": [{"id": "r1", "finished": True}, {"id": "r2", "finished": False},
                              {"id": "r3", "finished": True}]}),
        })
        resultat = ConnecteurFormbricks().executer_confirmee("analyser", survey_id="srv_1")
        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["total_reponses"] == 3
        assert resultat.detail["terminees"] == 2

    def test_analyse_sans_survey_id_est_un_echec(self):
        resultat = ConnecteurFormbricks().executer_confirmee("analyser", survey_id="")
        assert resultat.statut is Statut.ECHEC


class TestLeCoupeCircuitPublish:
    def test_creer_refuse_sous_publish_eteint_par_defaut(self):
        """PUBLISH est eteint par defaut dans le vrai `config/permissions.yaml`
        (verifie) : publier un sondage doit rester bloque tant qu'il ne l'a
        pas explicitement autorise — meme avec une instance configuree et
        joignable."""
        resultat = ConnecteurFormbricks().executer_confirmee(
            "creer", titre="t", question="q")
        assert resultat.statut is Statut.REFUSE
        assert FauxClient.appels == []


class TestLaVraiePolitiqueLivree:
    def test_creer_reste_sous_publish_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        politique = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE)
        regle_creer = politique.regle("formbricks", "survey")
        assert regle_creer is not None, "formbricks.survey a disparu de la politique livree"
        assert regle_creer.get("decision") == "CONFIRMATION"
        assert regle_creer.get("interrupteur") == "PUBLISH"

        regle_lire = politique.regle("formbricks", "read")
        assert regle_lire is not None
        assert regle_lire.get("decision") == "ALLOWED"
