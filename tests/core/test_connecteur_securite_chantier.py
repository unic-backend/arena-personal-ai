"""Le connecteur sécurité chantier : un appel HTTP vers SiteGuard (service
local séparé), jamais Ultralytics importé ici (AGPL-3.0, SA dépendance dans
SON processus — voir la docstring du module).

`FauxClient` simule ce qu'une vraie instance SiteGuard rendrait — jamais un
vrai serveur, absent pour ce propriétaire. Même pattern que
`tests/core/test_connecteur_formbricks.py`.
"""
import base64

import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.securite_chantier import ConnecteurSecuriteChantier

IMAGE_B64 = base64.b64encode(b"faux-jpeg-mais-suffit-pour-le-test").decode("ascii")


@pytest.fixture(autouse=True)
def _configuration(monkeypatch):
    monkeypatch.setenv("SITEGUARD_BASE_URL", "http://127.0.0.1:8000")


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
        FauxClient.appels.append(("GET", url))
        for suffixe, reponse in FauxClient.reponses_get.items():
            if url.endswith(suffixe):
                return reponse
        return FausseReponse(404)

    def post(self, url, files=None, **kw):
        FauxClient.appels.append(("POST", url, files))
        for suffixe, reponse in FauxClient.reponses_post.items():
            if url.endswith(suffixe):
                return reponse
        return FausseReponse(404)


@pytest.fixture(autouse=True)
def _reinitialiser_faux_client(monkeypatch):
    import core.connectors.securite_chantier as module
    FauxClient.reponses_get = {"/health": FausseReponse(200, {"status": "ok"})}
    FauxClient.reponses_post = {}
    FauxClient.appels = []
    monkeypatch.setattr(module.httpx, "Client", FauxClient)


class TestConfiguration:
    def test_sans_base_url_non_configure(self, monkeypatch):
        monkeypatch.delenv("SITEGUARD_BASE_URL", raising=False)
        sante = ConnecteurSecuriteChantier().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "SITEGUARD_BASE_URL" in sante.ce_qui_manque

    def test_aucune_url_par_defaut_n_est_devinee(self, monkeypatch):
        """Jamais une instance SiteGuard devinee a la place d'une instance
        non configuree (DEC-0002)."""
        monkeypatch.delenv("SITEGUARD_BASE_URL", raising=False)
        resultat = ConnecteurSecuriteChantier().executer_confirmee(
            "analyser", image_base64=IMAGE_B64)
        assert resultat.statut is Statut.NON_CONFIGURE
        assert FauxClient.appels == []


class TestSonde:
    def test_instance_joignable_operationnel(self):
        sante = ConnecteurSecuriteChantier().sonder()
        assert sante.etat is EtatSante.OPERATIONNEL

    def test_instance_en_panne(self):
        FauxClient.reponses_get = {"/health": FausseReponse(500)}
        sante = ConnecteurSecuriteChantier().sonder()
        assert sante.etat is EtatSante.EN_PANNE

    def test_instance_injoignable_non_configure(self, monkeypatch):
        import httpx

        import core.connectors.securite_chantier as module

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
        sante = ConnecteurSecuriteChantier().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE


class TestAnalyser:
    def test_detection_reelle(self):
        FauxClient.reponses_post = {
            "/api/v1/detection/image": FausseReponse(200, {
                "success": True,
                "detections": [{"class": "person", "confidence": 0.9, "bbox": [0, 0, 1, 1]},
                              {"class": "no_helmet", "confidence": 0.7, "bbox": [0, 0, 1, 1]}],
                "risks": [{"type": "no_helmet", "level": "high", "count": 1,
                          "message": "1 personne semble ne pas porter de casque."}],
            }),
        }
        resultat = ConnecteurSecuriteChantier().executer_confirmee(
            "analyser", image_base64=IMAGE_B64, nom_fichier="chantier.jpg")

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["personnes"] == 1
        assert resultat.detail["risques"][0]["niveau"] == "high"
        assert "casque" in resultat.message

        appel_post = [a for a in FauxClient.appels if a[0] == "POST"][0]
        assert appel_post[2]["file"][0] == "chantier.jpg"

    def test_sans_image_est_un_echec(self):
        resultat = ConnecteurSecuriteChantier().executer_confirmee("analyser", image_base64="")
        assert resultat.statut is Statut.ECHEC
        assert [a for a in FauxClient.appels if a[0] == "POST"] == []

    def test_image_non_base64_est_un_echec_jamais_un_crash(self):
        resultat = ConnecteurSecuriteChantier().executer_confirmee(
            "analyser", image_base64="!!!pas-du-base64!!!")
        assert resultat.statut is Statut.ECHEC

    def test_siteguard_refuse_est_un_echec(self):
        FauxClient.reponses_post = {
            "/api/v1/detection/image": FausseReponse(400, texte="format non supporte"),
        }
        resultat = ConnecteurSecuriteChantier().executer_confirmee(
            "analyser", image_base64=IMAGE_B64)
        assert resultat.statut is Statut.ECHEC
        assert "non supporte" in resultat.message

    def test_image_trop_volumineuse_est_un_echec(self, monkeypatch):
        import core.connectors.securite_chantier as module
        monkeypatch.setattr(module, "TAILLE_MAX_OCTETS", 4)
        resultat = ConnecteurSecuriteChantier().executer_confirmee(
            "analyser", image_base64=IMAGE_B64)
        assert resultat.statut is Statut.ECHEC
        assert "volumineuse" in resultat.message
        assert [a for a in FauxClient.appels if a[0] == "POST"] == []

    def test_aucun_element_detecte_reste_un_succes_honnete(self):
        FauxClient.reponses_post = {
            "/api/v1/detection/image": FausseReponse(200, {
                "success": True, "detections": [], "risks": [],
            }),
        }
        resultat = ConnecteurSecuriteChantier().executer_confirmee(
            "analyser", image_base64=IMAGE_B64)
        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["personnes"] == 0
        assert "Aucun élément" in resultat.message


class TestLaVraiePolitiqueLivree:
    def test_lire_reste_allowed_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("securite_chantier", "read")
        assert regle is not None, "securite_chantier.read a disparu de la politique livree"
        assert regle.get("decision") == "ALLOWED"


class TestJamaisUltralyticsImporte:
    """La frontiere de licence (AGPL-3.0 d'Ultralytics, SA dependance dans
    SON processus) : ce module ne doit jamais importer ultralytics/torch —
    seulement appeler SiteGuard par HTTP."""

    def test_aucun_import_ultralytics_ou_torch(self):
        import core.connectors.securite_chantier as module
        with open(module.__file__, encoding="utf-8") as f:
            contenu = f.read()
        assert "import ultralytics" not in contenu
        assert "import torch" not in contenu
