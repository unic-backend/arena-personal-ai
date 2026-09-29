"""« Connecter TikTok » (DEC-0186) : consentement, echange du code, jeton stocke.

Meme chemin que Gmail (`apps/backend/routers/connectors.py`), avec les gestes
de TikTok (`social/tiktok/oauth.py`). Aucun appel reseau : l'echange est
remplace, ou passe par un `httpx.MockTransport`.
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
from social.tiktok import oauth
from social.tiktok.tiktok_connector import URL_JETON

CLE = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    routeur._ETATS_EN_ATTENTE.clear()
    return TestClient(main.app, raise_server_exceptions=False)


class RegistreDouble:
    """Jamais le vrai connecteur : il appellerait TikTok pour de vrai."""

    def __init__(self) -> None:
        self.invalide = False

    def est_declare(self, nom: str) -> bool:
        return nom == "tiktok"

    def obtenir(self, nom: str):
        return self

    def invalider_sonde(self) -> None:
        self.invalide = True

    def sante(self, nom: str) -> Sante:
        return Sante(etat=EtatSante.OPERATIONNEL, message="Compte TikTok @unic_plaquiste joignable.")


@pytest.fixture
def application(monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "cle-app")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "secret-app")


def test_sans_application_tiktok_le_refus_dit_quoi_creer(client, monkeypatch):
    monkeypatch.delenv("TIKTOK_CLIENT_KEY", raising=False)
    monkeypatch.delenv("TIKTOK_CLIENT_SECRET", raising=False)

    r = client.get("/connectors/tiktok/auth", headers={"Authorization": f"Bearer {CLE}"})

    assert r.status_code == 409
    assert "developers.tiktok.com" in r.json()["detail"]
    assert "/connectors/tiktok/callback" in r.json()["detail"]


def test_le_consentement_demande_les_trois_portees_et_rien_d_autre(client, application):
    r = client.get("/connectors/tiktok/auth", headers={"Authorization": f"Bearer {CLE}"},
                   follow_redirects=False)

    assert r.status_code == 302
    cible = urlparse(r.headers["location"])
    assert f"{cible.scheme}://{cible.netloc}{cible.path}" == oauth.URL_AUTORISATION
    requete = parse_qs(cible.query)
    assert requete["client_key"] == ["cle-app"]
    assert requete["scope"] == ["user.info.basic,video.publish,video.upload"]
    assert requete["response_type"] == ["code"]
    assert requete["redirect_uri"][0].endswith("/connectors/tiktok/callback")
    etat = requete["state"][0]
    assert routeur._ETATS_EN_ATTENTE[etat][0] == "tiktok"


def test_le_retour_de_tiktok_stocke_le_jeton_de_renouvellement(client, application, monkeypatch, tmp_path):
    vus = []

    def echange(cle, secret, code, redirect):
        vus.append((cle, secret, code, redirect))
        return {"access_token": "act.1", "refresh_token": "rft.1", "expires_in": 86400}

    monkeypatch.setattr(oauth, "code_pour_jetons", echange)
    monkeypatch.setattr(routeur, "BASE_DIR", tmp_path / "sans-env")
    monkeypatch.setattr(routeur, "DB_PATH", tmp_path / "memoire.db")
    registre = RegistreDouble()
    monkeypatch.setattr(routeur, "registre", registre)
    # Une valeur d'avant, pour que monkeypatch la remette apres le test : le
    # routeur ecrit dans os.environ, et rien ne doit fuir vers les suivants.
    monkeypatch.setenv("TIKTOK_REFRESH_TOKEN", "avant")
    routeur._ETATS_EN_ATTENTE["t1"] = ("tiktok", routeur.time.monotonic() + 600)

    r = client.get("/connectors/tiktok/callback?code=CODE-1&state=t1")

    assert r.status_code == 200 and "usman_oauth_success" in r.text
    assert "@unic_plaquiste" in r.text and registre.invalide, "sonde fraiche apres connexion"
    assert vus[0][:3] == ("cle-app", "secret-app", "CODE-1")
    assert os.environ["TIKTOK_REFRESH_TOKEN"] == "rft.1"
    assert routeur.stockage_jetons.charger_tout(str(tmp_path / "memoire.db")) == {
        "TIKTOK_REFRESH_TOKEN": "rft.1"}
    assert "rft.1" not in r.text and "act.1" not in r.text, "aucun jeton vers le navigateur"


def test_un_state_de_gmail_ne_connecte_pas_tiktok(client, application, monkeypatch):
    monkeypatch.setattr(oauth, "code_pour_jetons", lambda *a: {"refresh_token": "rft.x"})
    routeur._ETATS_EN_ATTENTE["g1"] = ("gmail", routeur.time.monotonic() + 600)

    r = client.get("/connectors/tiktok/callback?code=C&state=g1")

    assert "expire ou deja utilise" in r.text


def test_un_refus_de_tiktok_est_dit_par_son_nom(client, application):
    r = client.get("/connectors/tiktok/callback?error=access_denied")

    assert "TikTok a refuse : access_denied" in r.text


# --- L'echange lui-meme -----------------------------------------------------------

def _transport(reponse: httpx.Response, vus: list) -> httpx.MockTransport:
    def repondre(requete: httpx.Request) -> httpx.Response:
        vus.append(requete)
        return reponse
    return httpx.MockTransport(repondre)


def test_l_echange_envoie_le_code_et_rend_les_jetons(monkeypatch):
    vus: list = []
    reel = httpx.Client
    monkeypatch.setattr(oauth.httpx, "Client", lambda **k: reel(transport=_transport(
        httpx.Response(200, json={"access_token": "a", "refresh_token": "r"}), vus)))

    jetons = oauth.code_pour_jetons("cle", "secret", "CODE", "https://arena.test/cb")

    assert jetons["refresh_token"] == "r"
    assert str(vus[0].url) == URL_JETON
    assert dict(httpx.QueryParams(vus[0].content.decode())) == {
        "client_key": "cle", "client_secret": "secret", "code": "CODE",
        "grant_type": "authorization_code", "redirect_uri": "https://arena.test/cb"}


def test_un_200_sans_jeton_de_renouvellement_est_un_refus(monkeypatch):
    """TikTok repond 200 avec une erreur dans le corps : ce n'est pas un succes."""
    reel = httpx.Client
    monkeypatch.setattr(oauth.httpx, "Client", lambda **k: reel(transport=_transport(
        httpx.Response(200, json={"error": "invalid_grant"}), [])))

    with pytest.raises(oauth.RefusTikTok, match="invalid_grant"):
        oauth.code_pour_jetons("cle", "secret", "CODE", "https://arena.test/cb")
