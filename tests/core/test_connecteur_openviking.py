"""Le connecteur OpenViking : un appel HTTP vers son propre serveur
(AGPLv3, service séparé), jamais son code importé — voir la docstring du
module. Même patron de faux client que
`tests/core/test_connecteur_securite_chantier.py`.
"""
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.openviking import ConnecteurOpenViking


@pytest.fixture(autouse=True)
def _configuration(monkeypatch):
    monkeypatch.setenv("OPENVIKING_URL", "http://127.0.0.1:1933")
    monkeypatch.delenv("OPENVIKING_API_KEY", raising=False)


class FausseReponse:
    def __init__(self, status_code=200, donnees=None, texte=""):
        self.status_code = status_code
        self._donnees = donnees or {}
        self.text = texte or str(donnees)

    def json(self):
        return self._donnees


class FauxClient:
    reponses_get: dict = {}
    reponses_post: dict = {}
    appels: list = []

    def __init__(self, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, **kw):
        FauxClient.appels.append(("GET", url, kw))
        for suffixe, reponse in FauxClient.reponses_get.items():
            if url.endswith(suffixe):
                return reponse
        return FausseReponse(404)

    def post(self, url, json=None, headers=None, **kw):
        FauxClient.appels.append(("POST", url, json, headers))
        for suffixe, reponse in FauxClient.reponses_post.items():
            if url.endswith(suffixe):
                return reponse
        return FausseReponse(404)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _reinitialiser_faux_client(monkeypatch):
    import core.connectors.openviking as module
    FauxClient.reponses_get = {"/health": FausseReponse(200, {"status": "ok"})}
    FauxClient.reponses_post = {}
    FauxClient.appels = []
    monkeypatch.setattr(module.httpx, "Client", FauxClient)


class TestConfiguration:
    def test_sans_url_non_configure(self, monkeypatch):
        monkeypatch.delenv("OPENVIKING_URL", raising=False)
        sante = ConnecteurOpenViking().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "OPENVIKING_URL" in sante.ce_qui_manque

    def test_aucune_url_par_defaut_n_est_devinee(self, monkeypatch):
        """DEC-0002 : jamais un serveur OpenViking deviné à la place d'un
        serveur non configuré."""
        monkeypatch.delenv("OPENVIKING_URL", raising=False)
        resultat = ConnecteurOpenViking().executer("contexte", requete="authentification")
        assert resultat.statut is Statut.NON_CONFIGURE
        assert FauxClient.appels == []


class TestSonde:
    def test_serveur_joignable_operationnel(self):
        assert ConnecteurOpenViking().sonder().etat is EtatSante.OPERATIONNEL

    def test_serveur_en_panne(self):
        FauxClient.reponses_get = {"/health": FausseReponse(500)}
        assert ConnecteurOpenViking().sonder().etat is EtatSante.EN_PANNE

    def test_serveur_injoignable_non_configure(self, monkeypatch):
        import httpx

        import core.connectors.openviking as module

        class ClientQuiEchoue:
            def __init__(self, **kw):
                pass

            def get(self, *a, **kw):
                raise httpx.ConnectError("refuse")

            def close(self):
                pass

        monkeypatch.setattr(module.httpx, "Client", ClientQuiEchoue)
        assert ConnecteurOpenViking().sonder().etat is EtatSante.NON_CONFIGURE


class TestAuthentification:
    def test_la_cle_voyage_dans_l_en_tete_quand_fournie(self, monkeypatch):
        monkeypatch.setenv("OPENVIKING_API_KEY", "une-vraie-cle")
        FauxClient.reponses_post = {
            "/api/v1/search/find": FausseReponse(200, {"result": {"total": 0}}),
        }
        ConnecteurOpenViking().executer("rechercher", requete="x")

        appel = [a for a in FauxClient.appels if a[0] == "POST"][0]
        assert appel[3]["Authorization"] == "Bearer une-vraie-cle"

    def test_sans_cle_aucun_en_tete_authorization(self):
        FauxClient.reponses_post = {
            "/api/v1/search/find": FausseReponse(200, {"result": {"total": 0}}),
        }
        ConnecteurOpenViking().executer("rechercher", requete="x")

        appel = [a for a in FauxClient.appels if a[0] == "POST"][0]
        assert "Authorization" not in appel[3]


class TestContexte:
    def test_contexte_assemble_est_rendu(self):
        FauxClient.reponses_post = {
            "/api/v1/search/search": FausseReponse(200, {"result": {
                "entries": [{"uri": "viking://user/default/memories/events/x.md",
                            "category": "events", "score": 0.9, "detail": "full", "text": "..."}],
                "rendered": "<memory ...>...</memory>",
                "digest": "", "stats": {"used_tokens": 120},
            }}),
        }
        resultat = ConnecteurOpenViking().executer("contexte", requete="pourquoi le pipeline video echoue")

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["rendu"] == "<memory ...>...</memory>"
        assert len(resultat.detail["entrees"]) == 1

        appel = [a for a in FauxClient.appels if a[0] == "POST"][0]
        assert appel[2]["mode"] == "context"
        assert appel[2]["query"] == "pourquoi le pipeline video echoue"

    def test_sans_question_est_un_echec(self):
        resultat = ConnecteurOpenViking().executer("contexte")
        assert resultat.statut is Statut.ECHEC
        assert [a for a in FauxClient.appels if a[0] == "POST"] == []

    def test_serveur_refuse_est_un_echec(self):
        FauxClient.reponses_post = {
            "/api/v1/search/search": FausseReponse(
                400, {"status": "error", "error": {"code": "INVALID_ARGUMENT", "message": "quotas invalides"}}),
        }
        resultat = ConnecteurOpenViking().executer("contexte", requete="x")
        assert resultat.statut is Statut.ECHEC
        assert "quotas invalides" in resultat.message


class TestRechercher:
    def test_recherche_reelle(self):
        FauxClient.reponses_post = {
            "/api/v1/search/find": FausseReponse(200, {"result": {
                "memories": [{"uri": "viking://user/default/memories/entities/x.md"}],
                "resources": [], "skills": [], "total": 1,
            }}),
        }
        resultat = ConnecteurOpenViking().executer("rechercher", requete="authentification")

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["total"] == 1
        assert len(resultat.detail["memoires"]) == 1


class TestCompetences:
    def test_competences_reelles(self):
        FauxClient.reponses_post = {
            "/api/v1/skills/find": FausseReponse(200, {"result": [{"name": "search-web"}]}),
        }
        resultat = ConnecteurOpenViking().executer("competences", requete="chercher sur internet")

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["competences"] == [{"name": "search-web"}]


class TestEcrireRessource:
    def test_ajout_reel(self):
        FauxClient.reponses_post = {
            "/api/v1/resources": FausseReponse(200, {"result": {"uri": "viking://resources/guide"}}),
        }
        resultat = ConnecteurOpenViking().executer(
            "ecrire_ressource", url="https://example.com/guide.md", raison="documentation utile")

        assert resultat.statut is Statut.SUCCES
        assert resultat.preuve == "viking://resources/guide"

    def test_sans_url_est_un_echec(self):
        resultat = ConnecteurOpenViking().executer("ecrire_ressource")
        assert resultat.statut is Statut.ECHEC
        assert [a for a in FauxClient.appels if a[0] == "POST"] == []


class TestLaVraiePolitiqueLivree:
    def test_lire_reste_allowed_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("openviking", "read")
        assert regle is not None, "openviking.read a disparu de la politique livrée"
        assert regle.get("decision") == "ALLOWED"


class TestJamaisLeCoeurAgplImporte:
    """La frontière de licence (AGPLv3 du cœur OpenViking) : ce module ne
    doit jamais importer quoi que ce soit du dépôt OpenViking — seulement
    l'appeler par HTTP."""

    def test_aucun_import_openviking(self):
        import core.connectors.openviking as module
        with open(module.__file__, encoding="utf-8") as f:
            contenu = f.read()
        assert "import openviking" not in contenu
        assert "from openviking" not in contenu
        assert "import ragfs" not in contenu
