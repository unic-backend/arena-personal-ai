"""La route qui rend la chronologie : fermee sans cle, honnete quand elle est vide.

Elle est livree en meme temps que le journal, et c'est deliberé : la table
`agent_logs` a passe des mois sans que rien ne l'ecrive **ni** ne la lise. Un
journal qu'on ne peut pas consulter reproduit exactement ce defaut.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main, runtime
from apps.backend import security as securite
from core.actions.journal import ActionEnregistree, EtatVerification, JournalDesActions

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def journal_isole(tmp_path, monkeypatch):
    """Un journal vide par test : la base du depot ne doit pas influencer le resultat."""
    journal = JournalDesActions(db_path=str(tmp_path / "journal.db"))
    monkeypatch.setattr(runtime, "journal", journal)
    monkeypatch.setattr("apps.backend.routers.actions.journal", journal)
    return journal


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """Client authentifie, avec un compteur de debit remis a zero.

    `securite.limiteur` est un compteur unique, partage par tout le module et
    donc par toute la suite. Sans cette remise a zero, ce fichier passait seul
    et echouait en 429 dans la suite complete : les onze requetes de ses tests
    s'ajoutaient a celles des autres fichiers, au-dela du plafond de dix. Le
    plafond fait son travail ; c'est l'isolement du test qui manquait.
    """
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def _action(**remplacements) -> ActionEnregistree:
    valeurs = {
        "outil": "tiktok", "action": "publish_video", "cible": "TikTok",
        "resultat": "NOT_CONFIGURED", "verification": EtatVerification.SANS_OBJET,
    }
    valeurs.update(remplacements)
    return ActionEnregistree(**valeurs)


# --- Fermeture ----------------------------------------------------------------

def test_sans_cle_la_route_refuse(client, journal_isole):
    assert client.get("/api/actions").status_code == 401


def test_avec_une_mauvaise_cle_la_route_refuse(client, journal_isole):
    res = client.get("/api/actions", headers={"Authorization": "Bearer faux"})

    assert res.status_code == 401


# --- Lecture ------------------------------------------------------------------

def test_un_journal_vide_repond_au_lieu_d_echouer(client, entetes, journal_isole):
    res = client.get("/api/actions", headers=entetes)

    assert res.status_code == 200
    assert res.json() == {"resume": {"total": 0, "avec_effet_verifie": 0}, "actions": []}


def test_les_actions_enregistrees_sont_rendues(client, entetes, journal_isole):
    journal_isole.enregistrer(_action())

    corps = client.get("/api/actions", headers=entetes).json()

    assert corps["resume"]["total"] == 1
    assert corps["actions"][0]["resultat"] == "NOT_CONFIGURED"
    assert corps["actions"][0]["verification"] == "NOT_APPLICABLE"


def test_la_limite_est_appliquee(client, entetes, journal_isole):
    for index in range(5):
        journal_isole.enregistrer(_action(cible=f"c{index}"))

    corps = client.get("/api/actions?limite=2", headers=entetes).json()

    assert len(corps["actions"]) == 2


def test_le_filtre_par_cible_fonctionne(client, entetes, journal_isole):
    journal_isole.enregistrer(_action(cible="TikTok"))
    journal_isole.enregistrer(_action(cible="Gmail"))

    corps = client.get("/api/actions?cible=Gmail", headers=entetes).json()

    assert [a["cible"] for a in corps["actions"]] == ["Gmail"]


@pytest.mark.parametrize("limite", [0, -1, 501, 10_000])
def test_une_limite_hors_bornes_est_refusee(client, entetes, journal_isole, limite):
    res = client.get(f"/api/actions?limite={limite}", headers=entetes)

    assert res.status_code == 422


# --- Aucun secret ne ressort par cette route ----------------------------------

def test_un_secret_journalise_ne_ressort_pas_par_l_api(client, entetes, journal_isole):
    journal_isole.enregistrer(_action(parametres={"access_token": "ya29.SECRET"}))

    assert "ya29.SECRET" not in client.get("/api/actions", headers=entetes).text
