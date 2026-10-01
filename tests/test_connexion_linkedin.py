"""« Connecter LinkedIn » (DEC-0209) : consentement, échange du code, jeton gardé.

Même chemin que Gmail et TikTok (`apps/backend/routers/connectors.py`), avec
les gestes de LinkedIn (`social/linkedin/oauth.py`). Aucun appel réseau :
l'échange est remplacé, ou passe par un `httpx.MockTransport`.

La différence qui compte : une application LinkedIn ordinaire ne reçoit pas de
jeton de renouvellement. C'est le jeton d'ACCÈS qui est gardé, et un corps sans
`access_token` est un refus, jamais un succès.
"""
import os
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import connectors as routeur
from core.connectors.base import EtatSante, Sante
from social.linkedin import oauth
from social.linkedin.linkedin_connector import LinkedInConnector

CLE = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    routeur._ETATS_EN_ATTENTE.clear()
    return TestClient(main.app, raise_server_exceptions=False)


class RegistreDouble:
    """Jamais le vrai connecteur : il appellerait LinkedIn pour de vrai."""

    def __init__(self) -> None:
        self.invalide = False

    def est_declare(self, nom: str) -> bool:
        return nom == "linkedin"

    def obtenir(self, nom: str):
        return self

    def invalider_sonde(self) -> None:
        self.invalide = True

    def sante(self, nom: str) -> Sante:
        return Sante(etat=EtatSante.OPERATIONNEL,
                     message="Compte LinkedIn de Ousmane Diop joignable.")


@pytest.fixture
def application(monkeypatch):
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "id-app")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "secret-app")


def test_sans_application_linkedin_le_refus_dit_ou_trouver_les_cles(client, monkeypatch):
    monkeypatch.delenv("LINKEDIN_CLIENT_ID", raising=False)
    monkeypatch.delenv("LINKEDIN_CLIENT_SECRET", raising=False)

    r = client.get("/connectors/linkedin/auth", headers={"Authorization": f"Bearer {CLE}"})

    assert r.status_code == 409
    assert "linkedin.com/developers" in r.json()["detail"]
    assert "/connectors/linkedin/callback" in r.json()["detail"]


def test_le_consentement_demande_les_trois_portees_et_pas_l_email(client, application):
    r = client.get("/connectors/linkedin/auth", headers={"Authorization": f"Bearer {CLE}"},
                   follow_redirects=False)

    assert r.status_code == 302
    cible = urlparse(r.headers["location"])
    assert f"{cible.scheme}://{cible.netloc}{cible.path}" == oauth.URL_AUTORISATION
    requete = parse_qs(cible.query)
    assert requete["client_id"] == ["id-app"]
    assert requete["scope"] == ["openid profile w_member_social"]
    assert requete["response_type"] == ["code"]
    assert requete["redirect_uri"][0].endswith("/connectors/linkedin/callback")
    assert routeur._ETATS_EN_ATTENTE[requete["state"][0]][0] == "linkedin"
    assert "email" not in requete["scope"][0]
    assert "+" not in cible.query, "les portees doivent etre separees par %20, pas par +"


def test_le_retour_de_linkedin_garde_le_jeton_d_acces(client, application, monkeypatch, tmp_path):
    vus = []

    def echange(client_id, secret, code, redirect):
        vus.append((client_id, secret, code, redirect))
        return {"access_token": "AQV-acces-1", "expires_in": 5184000,
                "scope": "openid,profile,w_member_social"}

    monkeypatch.setattr(oauth, "code_pour_jetons", echange)
    monkeypatch.setattr(routeur, "BASE_DIR", tmp_path / "sans-env")
    monkeypatch.setattr(routeur, "DB_PATH", tmp_path / "memoire.db")
    registre = RegistreDouble()
    monkeypatch.setattr(routeur, "registre", registre)
    # Une valeur d'avant, pour que monkeypatch la remette apres le test : le
    # routeur ecrit dans os.environ, et rien ne doit fuir vers les suivants.
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "avant")
    routeur._ETATS_EN_ATTENTE["l1"] = ("linkedin", routeur.time.monotonic() + 600)

    r = client.get("/connectors/linkedin/callback?code=CODE-1&state=l1")

    assert r.status_code == 200 and "usman_oauth_success" in r.text
    assert "Ousmane Diop" in r.text and registre.invalide, "sonde fraiche apres connexion"
    assert vus[0][:3] == ("id-app", "secret-app", "CODE-1")
    assert os.environ["LINKEDIN_ACCESS_TOKEN"] == "AQV-acces-1"
    assert routeur.stockage_jetons.charger_tout(str(tmp_path / "memoire.db")) == {
        "LINKEDIN_ACCESS_TOKEN": "AQV-acces-1"}
    assert "AQV-acces-1" not in r.text, "aucun jeton vers le navigateur"


def test_une_reponse_sans_jeton_d_acces_n_est_pas_une_connexion(client, application, monkeypatch, tmp_path):
    monkeypatch.setattr(oauth, "code_pour_jetons", lambda *a: {"expires_in": 5184000})
    monkeypatch.setattr(routeur, "BASE_DIR", tmp_path / "sans-env")
    monkeypatch.setattr(routeur, "DB_PATH", tmp_path / "memoire.db")
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "avant")
    routeur._ETATS_EN_ATTENTE["l2"] = ("linkedin", routeur.time.monotonic() + 600)

    r = client.get("/connectors/linkedin/callback?code=C&state=l2")

    assert "jeton d'acces" in r.text and "usman_oauth_success" not in r.text
    assert os.environ["LINKEDIN_ACCESS_TOKEN"] == "avant", "rien n'a ete ecrit"


def test_un_state_de_gmail_ne_connecte_pas_linkedin(client, application, monkeypatch):
    monkeypatch.setattr(oauth, "code_pour_jetons", lambda *a: {"access_token": "x"})
    routeur._ETATS_EN_ATTENTE["g1"] = ("gmail", routeur.time.monotonic() + 600)

    r = client.get("/connectors/linkedin/callback?code=C&state=g1")

    assert "expire ou deja utilise" in r.text


def test_un_refus_de_linkedin_est_dit_par_son_nom(client, application):
    r = client.get("/connectors/linkedin/callback?error=user_cancelled_authorize")

    assert "LinkedIn a refuse : user_cancelled_authorize" in r.text


def test_un_echange_refuse_se_rapporte_sans_planter(client, application, monkeypatch):
    def refuse(*a):
        raise oauth.RefusLinkedIn("invalid_request")

    monkeypatch.setattr(oauth, "code_pour_jetons", refuse)
    routeur._ETATS_EN_ATTENTE["l3"] = ("linkedin", routeur.time.monotonic() + 600)

    r = client.get("/connectors/linkedin/callback?code=C&state=l3")

    assert "LinkedIn a refuse l'echange du code" in r.text


# --- L'echange lui-meme -----------------------------------------------------------

def _transport(reponse: httpx.Response, vus: list) -> httpx.MockTransport:
    def repondre(requete: httpx.Request) -> httpx.Response:
        vus.append(requete)
        return reponse
    return httpx.MockTransport(repondre)


def _simuler(monkeypatch, reponse: httpx.Response, vus: list) -> None:
    reel = httpx.Client
    monkeypatch.setattr(oauth.httpx, "Client",
                        lambda **k: reel(transport=_transport(reponse, vus)))


def test_l_echange_envoie_le_code_et_rend_le_jeton(monkeypatch):
    vus: list = []
    _simuler(monkeypatch, httpx.Response(200, json={"access_token": "a", "expires_in": 1}), vus)

    jetons = oauth.code_pour_jetons("id", "secret", "CODE", "https://arena.test/cb")

    assert jetons["access_token"] == "a"
    assert str(vus[0].url) == oauth.URL_JETON
    assert dict(httpx.QueryParams(vus[0].content.decode())) == {
        "grant_type": "authorization_code", "code": "CODE", "client_id": "id",
        "client_secret": "secret", "redirect_uri": "https://arena.test/cb"}


@pytest.mark.parametrize("statut, corps, attendu", [
    (200, {"error": "invalid_grant"}, "invalid_grant"),
    (400, {"error": "invalid_request", "error_description": "bad redirect"}, "invalid_request"),
    (200, {"expires_in": 5}, "200"),
])
def test_un_corps_sans_jeton_d_acces_est_un_refus(monkeypatch, statut, corps, attendu):
    _simuler(monkeypatch, httpx.Response(statut, json=corps), [])

    with pytest.raises(oauth.RefusLinkedIn, match=attendu):
        oauth.code_pour_jetons("id", "secret", "CODE", "https://arena.test/cb")


def test_une_reponse_illisible_est_un_refus(monkeypatch):
    _simuler(monkeypatch, httpx.Response(502, text="<html>bad gateway</html>"), [])

    with pytest.raises(oauth.RefusLinkedIn, match="illisible"):
        oauth.code_pour_jetons("id", "secret", "CODE", "https://arena.test/cb")


# --- Le connecteur apres une connexion --------------------------------------------

def test_apres_une_connexion_la_sante_est_mesuree_de_nouveau(monkeypatch):
    """Sans `invalider_sonde`, une sonde faite avant la connexion (60 s de cache)
    resterait « non connecte » juste apres un consentement reussi."""
    appels: list = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        appels.append(requete.headers["authorization"])
        return httpx.Response(200, json={"sub": "m1", "name": "Ousmane Diop"})

    connecteur = LinkedInConnector(transport=httpx.MockTransport(repondre))
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "ancien")
    assert connecteur.sonder().etat == EtatSante.OPERATIONNEL
    connecteur.sonder()
    assert len(appels) == 1, "la deuxieme sonde vient du cache"

    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "nouveau")
    connecteur.invalider_sonde()
    assert connecteur.sonder().etat == EtatSante.OPERATIONNEL

    assert appels == ["Bearer ancien", "Bearer nouveau"]
