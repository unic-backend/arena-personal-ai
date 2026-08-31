"""`/connectors` : le vrai chemin CONNECT -> OAUTH -> CALLBACK -> jeton stocke.

Chaque test isole ce que le routeur touche reellement — `_ETATS_EN_ATTENTE`
(state CSRF), le registre (double, jamais le vrai `GmailConnector`), les
fonctions Google (doublees, aucun appel reseau) — pour que ce fichier passe
seul et dans la suite complete, sans dependre d'un `.env` reel.
"""
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import connectors as routeur
from core.connectors.base import EtatSante, Sante

CLE_DE_TEST = "cle-de-test"


class RegistreDouble:
    """Un registre minimal : seule `gmail` est declaree, sante configurable."""

    def __init__(self, sante: Sante) -> None:
        self._sante = sante

    def est_declare(self, nom: str) -> bool:
        return nom == "gmail"

    def sante(self, nom: str) -> Sante:
        return self._sante


@pytest.fixture
def registre_operationnel(monkeypatch):
    sante = Sante(etat=EtatSante.OPERATIONNEL,
                  message="Gmail repond pour saer@unicplaquiste.com : 12 message(s).")
    monkeypatch.setattr(routeur, "registre", RegistreDouble(sante))
    return sante


@pytest.fixture
def registre_non_configure(monkeypatch):
    # Le vrai `GmailConnector.sonder()` nomme deja ce qui manque dans son
    # message (`core/connectors/gmail.py`) : ce double reproduit cette forme
    # plutot qu'un message vide qui ne dependrait que de `ce_qui_manque`.
    sante = Sante(etat=EtatSante.NON_CONFIGURE,
                  message="Gmail n'est pas connecte : trois valeurs dans .env absente(s).",
                  ce_qui_manque="GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN")
    monkeypatch.setattr(routeur, "registre", RegistreDouble(sante))
    return sante


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """Client authentifie ; cle, debit et etats OAuth remis a zero par test."""
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    securite.limiteur._passages.clear()
    routeur._ETATS_EN_ATTENTE.clear()
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def _identifiants_presents() -> Any:
    return ("id-client", "secret-client", "")


def _identifiants_absents() -> Any:
    return ("", "", "")


# --- /auth ----------------------------------------------------------------------

def test_auth_sans_cle_refuse(client):
    r = client.get("/connectors/gmail/auth")
    assert r.status_code == 401


def test_auth_fournisseur_inconnu(client, entetes, monkeypatch):
    monkeypatch.setattr(routeur, "identifiants", _identifiants_presents)
    r = client.get("/connectors/notion/auth", headers=entetes)
    assert r.status_code == 404
    assert "notion" in r.json()["detail"]


def test_auth_sans_identifiants_google_rapporte_ce_qui_manque(client, entetes, monkeypatch):
    monkeypatch.setattr(routeur, "identifiants", _identifiants_absents)
    r = client.get("/connectors/gmail/auth", headers=entetes)
    assert r.status_code == 409
    assert "console.cloud.google.com" in r.json()["detail"]


def test_auth_redirige_vers_google_avec_un_state(client, entetes, monkeypatch):
    monkeypatch.setattr(routeur, "identifiants", _identifiants_presents)
    r = client.get("/connectors/gmail/auth", headers=entetes, follow_redirects=False)

    assert r.status_code == 302
    cible = r.headers["location"]
    assert cible.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=id-client" in cible
    assert "access_type=offline" in cible
    assert "prompt=consent" in cible
    assert len(routeur._ETATS_EN_ATTENTE) == 1


def test_auth_accepte_la_cle_en_parametre_pour_window_open(client, monkeypatch):
    """Une fenetre ouverte par `window.open()` ne pose jamais d'en-tete."""
    monkeypatch.setattr(routeur, "identifiants", _identifiants_presents)
    r = client.get(f"/connectors/gmail/auth?cle={CLE_DE_TEST}", follow_redirects=False)
    assert r.status_code == 302


def test_auth_mauvaise_cle_en_parametre_refuse(client, monkeypatch):
    monkeypatch.setattr(routeur, "identifiants", _identifiants_presents)
    r = client.get("/connectors/gmail/auth?cle=fausse", follow_redirects=False)
    assert r.status_code == 401


# --- /callback --------------------------------------------------------------------

def test_callback_google_refuse_le_consentement(client):
    r = client.get("/connectors/gmail/callback?error=access_denied")
    assert r.status_code == 200
    assert "access_denied" in r.text


def test_callback_sans_code_ni_state(client):
    r = client.get("/connectors/gmail/callback")
    assert "Reponse incomplete" in r.text


def test_callback_state_inconnu_est_refuse(client):
    r = client.get("/connectors/gmail/callback?code=abc&state=jamais-emis")
    assert "expire ou deja utilise" in r.text


def test_callback_state_pour_un_autre_fournisseur_est_refuse(client):
    routeur._ETATS_EN_ATTENTE["s1"] = ("gmail", routeur.time.monotonic() + 600)
    r = client.get("/connectors/autrechose/callback?code=abc&state=s1")
    assert "n'a pas de flux OAuth cable" in r.text


def test_callback_echange_reussi_persiste_le_jeton(
    client, monkeypatch, tmp_path, registre_operationnel,
):
    monkeypatch.setattr(routeur, "identifiants", _identifiants_presents)
    monkeypatch.setattr(routeur, "code_pour_jetons",
                        lambda *a, **k: {"refresh_token": "rt-1234", "access_token": "at"})
    fichier_env = tmp_path / ".env"
    fichier_env.write_text("USMAN_API_KEY=x\n", encoding="utf-8")
    monkeypatch.setattr(routeur, "BASE_DIR", tmp_path)
    monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

    routeur._ETATS_EN_ATTENTE["s1"] = ("gmail", routeur.time.monotonic() + 600)
    r = client.get("/connectors/gmail/callback?code=abc123&state=s1")

    assert r.status_code == 200
    assert "usman_oauth_success" in r.text
    assert "saer@unicplaquiste.com" in r.text
    # Le state est consomme : un rejeu du meme lien echoue.
    assert "s1" not in routeur._ETATS_EN_ATTENTE
    # Effet immediat, sans redemarrage.
    assert os.environ["GOOGLE_REFRESH_TOKEN"] == "rt-1234"
    # Et persiste sur disque pour survivre a un redemarrage.
    assert "GOOGLE_REFRESH_TOKEN=rt-1234" in fichier_env.read_text(encoding="utf-8")


def test_callback_sans_env_sur_disque_ne_leve_pas(client, monkeypatch, tmp_path, registre_operationnel):
    """Deploiement hebergee (Railway...) : pas de fichier .env sur le disque —
    persister doit rester silencieux, jamais casser une connexion reussie."""
    monkeypatch.setattr(routeur, "identifiants", _identifiants_presents)
    monkeypatch.setattr(routeur, "code_pour_jetons",
                        lambda *a, **k: {"refresh_token": "rt-999"})
    monkeypatch.setattr(routeur, "BASE_DIR", tmp_path / "dossier-vide")
    monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

    routeur._ETATS_EN_ATTENTE["s2"] = ("gmail", routeur.time.monotonic() + 600)
    r = client.get("/connectors/gmail/callback?code=abc&state=s2")

    assert r.status_code == 200
    assert os.environ["GOOGLE_REFRESH_TOKEN"] == "rt-999"


def test_callback_google_refuse_l_echange(client, monkeypatch):
    monkeypatch.setattr(routeur, "identifiants", _identifiants_presents)

    def _leve(*a, **k):
        raise ConnectionError("boom")

    monkeypatch.setattr(routeur, "code_pour_jetons", _leve)
    routeur._ETATS_EN_ATTENTE["s3"] = ("gmail", routeur.time.monotonic() + 600)
    r = client.get("/connectors/gmail/callback?code=abc&state=s3")
    assert "refuse l'echange" in r.text


def test_callback_sans_refresh_token_est_signale(client, monkeypatch):
    monkeypatch.setattr(routeur, "identifiants", _identifiants_presents)
    monkeypatch.setattr(routeur, "code_pour_jetons", lambda *a, **k: {"access_token": "at"})
    routeur._ETATS_EN_ATTENTE["s4"] = ("gmail", routeur.time.monotonic() + 600)
    r = client.get("/connectors/gmail/callback?code=abc&state=s4")
    assert "n'a pas renvoye de jeton" in r.text


# --- /status ----------------------------------------------------------------------

def test_status_sans_cle_refuse(client):
    r = client.get("/connectors/gmail/status")
    assert r.status_code == 401


def test_status_fournisseur_inconnu(client, entetes):
    r = client.get("/connectors/postgres/status", headers=entetes)
    assert r.status_code == 404


def test_status_connecte_reflete_la_sonde_reelle(client, entetes, registre_operationnel):
    r = client.get("/connectors/gmail/status", headers=entetes)
    corps = r.json()
    assert corps["connected"] is True
    assert corps["verified"] is True
    assert "saer@unicplaquiste.com" in corps["account"]


def test_status_non_configure_ne_pretend_pas_etre_connecte(client, entetes, registre_non_configure):
    r = client.get("/connectors/gmail/status", headers=entetes)
    corps = r.json()
    assert corps["connected"] is False
    assert corps["account"] is None
    assert "trois valeurs" in corps["message"]


# --- /disconnect --------------------------------------------------------------------

def test_disconnect_sans_cle_refuse(client):
    r = client.post("/connectors/gmail/disconnect")
    assert r.status_code == 401


def test_disconnect_efface_uniquement_le_refresh_token(client, entetes, monkeypatch, tmp_path):
    monkeypatch.setattr(routeur, "BASE_DIR", tmp_path)
    (tmp_path / ".env").write_text(
        "GOOGLE_CLIENT_ID=id\nGOOGLE_CLIENT_SECRET=secret\nGOOGLE_REFRESH_TOKEN=ancien\n",
        encoding="utf-8",
    )
    os.environ["GOOGLE_REFRESH_TOKEN"] = "ancien"

    r = client.post("/connectors/gmail/disconnect", headers=entetes)

    assert r.status_code == 200
    assert r.json() == {"connected": False}
    contenu = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "GOOGLE_REFRESH_TOKEN=\n" in contenu
    assert "GOOGLE_CLIENT_ID=id" in contenu  # le client OAuth reste : on ne le supprime pas
