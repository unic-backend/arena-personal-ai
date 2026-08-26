"""Limitation de débit : la fenêtre glissante, puis son effet sur l'API.

L'horloge est injectée : aucun test n'attend réellement.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend.rate_limit import LimiteurDebit


class HorlogeFactice:
    """Horloge que le test fait avancer lui-même."""

    def __init__(self, depart: float = 1000.0):
        self.instant = depart

    def __call__(self) -> float:
        return self.instant

    def avancer(self, secondes: float) -> None:
        self.instant += secondes


# --- La fenêtre glissante ------------------------------------------------------

def test_les_requetes_sous_le_plafond_passent():
    limiteur = LimiteurDebit(3, 60, horloge=HorlogeFactice())

    assert [limiteur.secondes_a_attendre("a") for _ in range(3)] == [None, None, None]


def test_la_requete_de_trop_est_refusee():
    limiteur = LimiteurDebit(3, 60, horloge=HorlogeFactice())
    for _ in range(3):
        limiteur.secondes_a_attendre("a")

    attente = limiteur.secondes_a_attendre("a")

    assert attente is not None
    assert attente == pytest.approx(60.0)


def test_le_plafond_se_libere_quand_la_fenetre_glisse():
    horloge = HorlogeFactice()
    limiteur = LimiteurDebit(2, 60, horloge=horloge)
    limiteur.secondes_a_attendre("a")
    limiteur.secondes_a_attendre("a")
    assert limiteur.secondes_a_attendre("a") is not None

    horloge.avancer(61)

    assert limiteur.secondes_a_attendre("a") is None


def test_une_requete_refusee_ne_repousse_pas_l_echeance():
    """Sinon un client bloqué se re-pénaliserait sans jamais pouvoir sortir."""
    horloge = HorlogeFactice()
    limiteur = LimiteurDebit(1, 60, horloge=horloge)
    limiteur.secondes_a_attendre("a")

    horloge.avancer(30)
    limiteur.secondes_a_attendre("a")   # refusée
    horloge.avancer(31)                 # 61 s après la première

    assert limiteur.secondes_a_attendre("a") is None


def test_les_clients_sont_comptes_separement():
    limiteur = LimiteurDebit(1, 60, horloge=HorlogeFactice())
    limiteur.secondes_a_attendre("a")

    assert limiteur.secondes_a_attendre("b") is None
    assert limiteur.secondes_a_attendre("a") is not None


def test_le_delai_annonce_decroit_avec_le_temps():
    horloge = HorlogeFactice()
    limiteur = LimiteurDebit(1, 60, horloge=horloge)
    limiteur.secondes_a_attendre("a")

    horloge.avancer(50)

    assert limiteur.secondes_a_attendre("a") == pytest.approx(10.0)


def test_le_compteur_restant_est_exact():
    limiteur = LimiteurDebit(3, 60, horloge=HorlogeFactice())

    assert limiteur.restantes("a") == 3
    limiteur.secondes_a_attendre("a")
    assert limiteur.restantes("a") == 2


def test_le_nettoyage_libere_les_clients_inactifs():
    """Sans nettoyage, la table grandirait indéfiniment au fil des adresses."""
    horloge = HorlogeFactice()
    limiteur = LimiteurDebit(5, 60, horloge=horloge)
    for i in range(100):
        limiteur.secondes_a_attendre(f"client-{i}")

    horloge.avancer(61)

    assert limiteur.nettoyer() == 100
    assert limiteur._passages == {}


def test_le_nettoyage_epargne_les_clients_actifs():
    horloge = HorlogeFactice()
    limiteur = LimiteurDebit(5, 60, horloge=horloge)
    limiteur.secondes_a_attendre("ancien")
    horloge.avancer(61)
    limiteur.secondes_a_attendre("recent")

    limiteur.nettoyer()

    assert list(limiteur._passages) == ["recent"]


@pytest.mark.parametrize("requetes_max, fenetre", [(0, 60), (-1, 60), (5, 0), (5, -1)])
def test_une_configuration_absurde_est_refusee(requetes_max, fenetre):
    with pytest.raises(ValueError):
        LimiteurDebit(requetes_max, fenetre)


# --- Effet sur l'API -----------------------------------------------------------

CLE = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE}"}


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "ARENA_API_KEY", CLE)
    monkeypatch.setattr(main, "REQUETES_MAX", 3)
    monkeypatch.setattr(main, "limiteur", LimiteurDebit(3, 60, horloge=HorlogeFactice()))
    return TestClient(main.app, raise_server_exceptions=False)


def test_la_route_de_chat_refuse_au_dela_du_plafond(client):
    for _ in range(3):
        assert client.post("/api/chat", json={"prompt": "x"}, headers=ENTETES).status_code != 429

    res = client.post("/api/chat", json={"prompt": "x"}, headers=ENTETES)

    assert res.status_code == 429
    assert "Retry-After" in res.headers
    assert int(res.headers["Retry-After"]) > 0


def test_la_passerelle_v1_est_limitee_aussi(client):
    for _ in range(3):
        client.post("/v1/chat/completions", json={"model": "arena-core", "messages": []},
                    headers=ENTETES)

    res = client.post("/v1/chat/completions", json={"model": "arena-core", "messages": []},
                      headers=ENTETES)

    assert res.status_code == 429


def test_les_routes_de_lecture_ne_sont_pas_limitees(client):
    """`/health` sert aux sondes : le limiter le rendrait inutile."""
    for _ in range(20):
        assert client.get("/health").status_code == 200


def test_l_authentification_passe_avant_la_limitation(client):
    """Une requête sans clé doit être refusée sans consommer le quota."""
    for _ in range(10):
        assert client.post("/api/chat", json={"prompt": "x"}).status_code == 401

    assert client.post("/api/chat", json={"prompt": "x"}, headers=ENTETES).status_code != 429


# --- Journalisation des refus d'authentification -------------------------------

def test_un_refus_d_authentification_est_journalise(client, caplog):
    with caplog.at_level("WARNING", logger="arena.backend"):
        client.post("/api/chat", json={"prompt": "x"}, headers={"Authorization": "Bearer faux"})

    messages = [e.getMessage() for e in caplog.records]
    assert any("Authentification refusee" in m for m in messages)
    assert any("/api/chat" in m for m in messages)


def test_le_journal_ne_contient_jamais_la_cle_presentee(client, caplog):
    """Un journal qui contient des secrets est un secret de plus à protéger."""
    cle_presentee = "valeur" + "-secrete-" + "presentee"

    with caplog.at_level("WARNING", logger="arena.backend"):
        client.post("/api/chat", json={"prompt": "x"},
                    headers={"Authorization": f"Bearer {cle_presentee}"})

    journal = " ".join(e.getMessage() for e in caplog.records)
    assert cle_presentee not in journal
    assert CLE not in journal


def test_un_depassement_de_debit_est_journalise(client, caplog):
    for _ in range(3):
        client.post("/api/chat", json={"prompt": "x"}, headers=ENTETES)

    with caplog.at_level("WARNING", logger="arena.backend"):
        client.post("/api/chat", json={"prompt": "x"}, headers=ENTETES)

    assert any("Debit depasse" in e.getMessage() for e in caplog.records)
