"""Les routes de confirmation : lire, confirmer, annuler — et jamais deux fois.

Le test qui compte le plus est `test_confirmer_deux_fois_n_execute_qu_une_fois` :
c'est la verification que le plan demande pour cette phase, et c'est aussi ce
qu'un double clic produit dans la vraie vie.

Ces tests ne joignent aucun service : l'executeur est un espion.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main, runtime
from apps.backend import security as securite
from core.actions.attente import FileDAttente
from core.actions.resultat import succes

CLE_DE_TEST = "cle-de-test"


class ExecuteurEspion:
    def __init__(self):
        self.appels = []

    def __call__(self, connecteur, capacite, compte=None, **parametres):
        self.appels.append((connecteur, capacite, compte, parametres))
        return succes(capacite, connecteur, "Envoye.", "msg-id-42")


@pytest.fixture
def executeur():
    return ExecuteurEspion()


@pytest.fixture
def file(tmp_path, executeur, monkeypatch):
    """Une file isolee, branchee sur la route comme sur le runtime."""
    file = FileDAttente(db_path=str(tmp_path / "attente.db"), executeur=executeur)
    monkeypatch.setattr(runtime, "file_attente", file)
    monkeypatch.setattr("apps.backend.routers.actions.file_attente", file)
    return file


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """Client authentifie, compteur de debit remis a zero (compteur partage)."""
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def _deposer(file, **remplacements):
    valeurs = {
        "action": "Envoie le devis UC-2026-0827",
        "cible": "client@exemple.sn",
        "risque": "HIGH",
        "resultat_attendu": "Un e-mail part vers le client avec le devis joint.",
        "connecteur": "gmail",
        "capacite": "send",
        "parametres": {"objet": "Devis"},
    }
    valeurs.update(remplacements)
    return file.deposer(**valeurs)


# --- Fermeture ----------------------------------------------------------------

@pytest.mark.parametrize("methode,chemin", [
    ("get", "/api/actions/pending"),
    ("post", "/api/actions/abc/confirm"),
    ("post", "/api/actions/abc/cancel"),
    ("get", "/api/permissions"),
])
def test_sans_cle_les_routes_refusent(client, file, methode, chemin):
    assert getattr(client, methode)(chemin).status_code == 401


def test_une_confirmation_sans_cle_n_execute_rien(client, file, executeur):
    action = _deposer(file)

    client.post(f"/api/actions/{action.identifiant}/confirm")

    assert executeur.appels == []


# --- Lire la file -------------------------------------------------------------

def test_une_file_vide_repond_au_lieu_d_echouer(client, entetes, file):
    res = client.get("/api/actions/pending", headers=entetes)

    assert res.status_code == 200
    assert res.json() == {"total": 0, "actions": []}


def test_les_actions_en_attente_portent_les_quatre_champs(client, entetes, file):
    _deposer(file)

    action = client.get("/api/actions/pending", headers=entetes).json()["actions"][0]

    assert action["action"] == "Envoie le devis UC-2026-0827"
    assert action["cible"] == "client@exemple.sn"
    assert action["risque"] == "HIGH"
    assert "devis joint" in action["resultat_attendu"]
    assert action["etat"] == "PENDING"


def test_lister_n_execute_rien(client, entetes, file, executeur):
    _deposer(file)

    client.get("/api/actions/pending", headers=entetes)

    assert executeur.appels == []


# --- Confirmer ----------------------------------------------------------------

def test_confirmer_execute_et_rend_la_preuve(client, entetes, file, executeur):
    action = _deposer(file)

    res = client.post(f"/api/actions/{action.identifiant}/confirm", headers=entetes)

    assert res.status_code == 200
    assert res.json()["status"] == "SUCCESS"
    assert res.json()["preuve"] == "msg-id-42"
    assert len(executeur.appels) == 1


def test_confirmer_deux_fois_n_execute_qu_une_fois(client, entetes, file, executeur):
    """La verification demandee par le plan pour cette phase."""
    action = _deposer(file)

    premier = client.post(f"/api/actions/{action.identifiant}/confirm", headers=entetes)
    second = client.post(f"/api/actions/{action.identifiant}/confirm", headers=entetes)

    assert len(executeur.appels) == 1
    assert premier.json()["status"] == "SUCCESS"
    assert second.json()["status"] == "FAILED"
    assert second.json()["a_eu_lieu"] is False


def test_la_seconde_reponse_rappelle_le_resultat_de_la_premiere(client, entetes, file):
    action = _deposer(file)
    client.post(f"/api/actions/{action.identifiant}/confirm", headers=entetes)

    second = client.post(f"/api/actions/{action.identifiant}/confirm", headers=entetes)

    assert "SUCCESS" in second.json()["response"]


def test_l_action_disparait_de_la_file_apres_confirmation(client, entetes, file):
    action = _deposer(file)
    client.post(f"/api/actions/{action.identifiant}/confirm", headers=entetes)

    assert client.get("/api/actions/pending", headers=entetes).json()["total"] == 0


def test_confirmer_un_identifiant_inconnu_rend_404(client, entetes, file, executeur):
    res = client.post("/api/actions/jamais-depose/confirm", headers=entetes)

    assert res.status_code == 404
    assert executeur.appels == []


def test_une_action_perimee_repond_200_en_disant_qu_elle_n_est_pas_partie(
    client, entetes, tmp_path, executeur, monkeypatch
):
    """Le code HTTP porte le sort de la requete, le corps porte celui de l'action."""
    perimee = FileDAttente(db_path=str(tmp_path / "p.db"), executeur=executeur, delai_heures=0)
    monkeypatch.setattr("apps.backend.routers.actions.file_attente", perimee)
    action = _deposer(perimee)

    res = client.post(f"/api/actions/{action.identifiant}/confirm", headers=entetes)

    assert res.status_code == 200
    assert res.json()["status"] == "FAILED"
    assert "expire" in res.json()["response"]
    assert executeur.appels == []


# --- Annuler ------------------------------------------------------------------

def test_annuler_empeche_toute_execution(client, entetes, file, executeur):
    action = _deposer(file)

    res = client.post(f"/api/actions/{action.identifiant}/cancel", headers=entetes)

    assert res.status_code == 200
    assert res.json()["annulee"] is True
    assert res.json()["etat"] == "CANCELLED"
    assert executeur.appels == []


def test_une_action_annulee_ne_peut_plus_partir(client, entetes, file, executeur):
    action = _deposer(file)
    client.post(f"/api/actions/{action.identifiant}/cancel", headers=entetes)

    res = client.post(f"/api/actions/{action.identifiant}/confirm", headers=entetes)

    assert res.json()["status"] == "FAILED"
    assert executeur.appels == []


def test_annuler_deux_fois_ne_ment_pas(client, entetes, file):
    action = _deposer(file)
    client.post(f"/api/actions/{action.identifiant}/cancel", headers=entetes)

    second = client.post(f"/api/actions/{action.identifiant}/cancel", headers=entetes)

    assert second.json()["annulee"] is False
    assert "deja" in second.json()["message"]


def test_annuler_un_identifiant_inconnu_rend_404(client, entetes, file):
    assert client.post("/api/actions/inconnu/cancel", headers=entetes).status_code == 404


def test_une_action_annulee_disparait_de_la_file(client, entetes, file):
    action = _deposer(file)
    client.post(f"/api/actions/{action.identifiant}/cancel", headers=entetes)

    assert client.get("/api/actions/pending", headers=entetes).json()["total"] == 0


# --- Voir ce qu'ARENA a le droit de faire -------------------------------------

def test_les_permissions_sont_lisibles(client, entetes, file):
    corps = client.get("/api/permissions", headers=entetes).json()

    assert corps["services"]["email"]["send"]["decision"] == "CONFIRMATION"
    assert corps["services"]["email"]["read"]["decision"] == "ALLOWED"


def test_les_permissions_montrent_le_coupe_circuit_qui_gouverne(client, entetes, file):
    corps = client.get("/api/permissions", headers=entetes).json()

    assert corps["services"]["social"]["publish"]["coupe_circuit"] == "PUBLISH"
    assert corps["services"]["email"]["read"]["coupe_circuit"] is None


def test_les_permissions_montrent_l_etat_des_coupe_circuits(client, entetes, file):
    corps = client.get("/api/permissions", headers=entetes).json()

    assert corps["coupe_circuits"]["PUBLISH"] is False
    assert corps["coupe_circuits"]["DELETE"] is False


def test_un_coupe_circuit_eteint_se_voit_dans_la_decision(client, entetes, file):
    """Publier est CONFIRMATION dans le fichier, DENIED en pratique : c'est la
    seconde valeur qui est affichee."""
    social = client.get("/api/permissions", headers=entetes).json()["services"]["social"]

    assert social["publish"]["decision"] == "DENIED"
    assert social["publish"]["origine"] == "coupe-circuit:PUBLISH"


def test_aucun_secret_ne_ressort_par_les_routes(client, entetes, file):
    _deposer(file, parametres={"objet": "Devis"})

    for chemin in ("/api/actions/pending", "/api/permissions"):
        assert "SECRET" not in client.get(chemin, headers=entetes).text
