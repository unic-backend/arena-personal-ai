"""Suivre UNE demande de bout en bout : l'en-tete HTTP jusqu'aux actions du journal.

Le defaut mesure le 13/09/2026 : quand le proprietaire disait « ce truc de ce
matin n'a pas marche », il fallait lire trente actions pour deviner lesquelles
venaient de sa phrase. `/api/actions?request_id=…` rend maintenant exactement
les quatre siennes.

Ces tests traversent la vraie chaine — middleware, journal SQLite, route — et
non un double qui rejouerait sa propre logique.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from apps.backend import main, runtime
from apps.backend import security as securite
from apps.backend.routers import actions as routeur_actions
from core.actions.journal import ActionEnregistree, JournalDesActions
from core.observabilite.fil import ENTETE

CLE_DE_TEST = "cle-de-test"
CHEMIN_ESSAI = "/essai/deux-actions"


@pytest.fixture
def journal(tmp_path, monkeypatch) -> JournalDesActions:
    """Un journal isole — ces tests ne touchent jamais data/database/memory.db."""
    reel = JournalDesActions(db_path=str(tmp_path / "journal.db"))
    monkeypatch.setattr(routeur_actions, "journal", reel)
    monkeypatch.setattr(runtime, "journal", reel)
    return reel


@pytest.fixture
def client(monkeypatch, journal) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    # Compteur de debit partage entre tous les fichiers de test : sans cette
    # remise a zero, ce fichier echoue des que la session depasse 60 requetes.
    securite.limiteur._passages.clear()
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


@pytest.fixture(autouse=True)
def route_d_essai(journal):
    """Une route qui agit deux fois, comme un connecteur le ferait.

    Elle est ajoutee ici plutot que dans `main.py` : une route d'essai livree
    dans l'application serait une surface de plus a proteger, pour rien.
    """
    async def deux_actions():
        journal.enregistrer(ActionEnregistree(
            outil="gmail", action="send", cible="fast@group", resultat="SUCCESS"))
        journal.enregistrer(ActionEnregistree(
            outil="devis", action="pdf", cible="UC-2026-0913", resultat="SUCCESS"))
        return {"ok": True}

    main.app.get(CHEMIN_ESSAI)(deux_actions)
    yield
    # La route est retiree : la laisser ferait grossir la surface d'API a chaque
    # test, et `tests/test_surface_api.py` l'epingle a l'exact.
    main.app.router.routes = [
        r for r in main.app.router.routes
        if getattr(r, "path", None) != CHEMIN_ESSAI
    ]


# --------------------------------------------------------------------------
# L'en-tete, a l'aller et au retour
# --------------------------------------------------------------------------

def test_toute_reponse_porte_un_identifiant_de_demande(client):
    reponse = client.get("/health")

    assert reponse.headers.get(ENTETE), f"{ENTETE} absent de la reponse"


def test_l_identifiant_du_client_est_rendu_tel_quel(client):
    """C'est ce qui permet de recoller une trace cote client."""
    reponse = client.get("/health", headers={ENTETE: "trace-du-client-42"})

    assert reponse.headers[ENTETE] == "trace-du-client-42"


def test_un_identifiant_mal_forme_est_remplace_sans_refuser_la_demande(client):
    """Un en-tete hostile n'est pas une raison de ne pas servir quelqu'un."""
    reponse = client.get("/health", headers={ENTETE: "faux\r\nX-Injecte: oui"})

    assert reponse.status_code == 200
    rendu = reponse.headers[ENTETE]
    assert "\n" not in rendu and "\r" not in rendu
    assert rendu != "faux"


def test_deux_demandes_recoivent_deux_identifiants_differents(client):
    premier = client.get("/health").headers[ENTETE]
    second = client.get("/health").headers[ENTETE]

    assert premier != second


def test_l_entete_est_expose_au_navigateur():
    """Recu mais non expose, le navigateur interdit au code de la page de le
    lire : l'identifiant existerait des deux cotes sans pouvoir etre rapproche."""
    cors = [c for c in main.app.user_middleware if "CORS" in str(c)]

    assert cors, "le middleware CORS a disparu"
    options = cors[0].kwargs
    assert ENTETE in options.get("expose_headers", []), (
        f"{ENTETE} n'est pas dans expose_headers"
    )
    assert ENTETE in options.get("allow_headers", []), (
        f"{ENTETE} n'est pas dans allow_headers : le PREFLIGHT rendrait 400"
    )


# --------------------------------------------------------------------------
# Le journal porte le fil, sans que personne le lui passe
# --------------------------------------------------------------------------

def test_les_actions_d_une_demande_portent_son_identifiant(client, entetes, journal):
    fil = client.get(CHEMIN_ESSAI, headers={ENTETE: "demande-du-matin"}).headers[ENTETE]

    assert fil == "demande-du-matin"
    assert [a.requete for a in journal.dernieres()] == [fil, fil]


def test_une_demande_retrouve_exactement_ses_actions(client, entetes):
    """Le coeur : deux demandes identiques, quatre actions, aucun melange."""
    premier = client.get(CHEMIN_ESSAI).headers[ENTETE]
    second = client.get(CHEMIN_ESSAI).headers[ENTETE]

    du_premier = client.get(f"/api/actions?request_id={premier}", headers=entetes).json()
    du_second = client.get(f"/api/actions?request_id={second}", headers=entetes).json()
    tout = client.get("/api/actions", headers=entetes).json()

    assert len(tout["actions"]) == 4
    assert len(du_premier["actions"]) == 2
    assert len(du_second["actions"]) == 2
    assert {a["requete"] for a in du_premier["actions"]} == {premier}
    assert {a["requete"] for a in du_second["actions"]} == {second}


def test_un_identifiant_inconnu_rend_une_liste_vide_pas_une_erreur(client, entetes):
    reponse = client.get("/api/actions?request_id=jamais-vu", headers=entetes)

    assert reponse.status_code == 200
    assert reponse.json()["actions"] == []


def test_hors_demande_l_action_n_a_pas_de_fil_invente(journal):
    """Un script ou une tache de fond n'a pas de demande derriere lui."""
    journal.enregistrer(ActionEnregistree(
        outil="script", action="run", cible="local", resultat="SUCCESS"))

    assert journal.dernieres()[0].requete is None


def test_la_chronologie_rend_le_fil_en_json(client, entetes):
    client.get(CHEMIN_ESSAI, headers={ENTETE: "trace-lisible"})

    ligne = client.get("/api/actions", headers=entetes).json()["actions"][0]

    assert ligne["requete"] == "trace-lisible"


def test_le_fil_reste_hors_du_tableau_texte():
    """32 caracteres par ligne rendraient la chronologie illisible pour
    l'humain qu'elle sert. Le contre-test de la decision ci-dessus."""
    from core.actions.timeline import COLONNES

    assert "requete" not in COLONNES


# --------------------------------------------------------------------------
# La base d'avant la migration survit
# --------------------------------------------------------------------------

def test_une_base_d_avant_la_colonne_est_migree_sans_rien_perdre(tmp_path):
    """Zone verrouillee : « une migration qui n'efface rien »."""
    chemin = tmp_path / "ancien.db"
    with sqlite3.connect(chemin) as connexion:
        connexion.execute("""CREATE TABLE journal_actions (
            identifiant TEXT PRIMARY KEY, horodatage TEXT NOT NULL, outil TEXT NOT NULL,
            action TEXT NOT NULL, cible TEXT NOT NULL, parametres TEXT NOT NULL,
            niveau_permission TEXT NOT NULL, resultat TEXT NOT NULL, erreurs TEXT,
            verification TEXT NOT NULL, preuve TEXT)""")
        connexion.execute(
            "INSERT INTO journal_actions VALUES ('ancien','2026-09-01T10:00:00+00:00',"
            "'gmail','send','client@x','{}','ALLOWED','SUCCESS',NULL,'VERIFIED',NULL)")

    journal = JournalDesActions(db_path=str(chemin))
    relu = journal.lire("ancien")

    assert relu is not None, "l'action d'avant la migration a disparu"
    assert relu.outil == "gmail" and relu.resultat == "SUCCESS"
    assert relu.requete is None, (
        "une action d'avant le fil n'en a jamais eu : lui en inventer un "
        "fabriquerait une trace"
    )


def test_une_action_d_avant_le_fil_n_est_rendue_par_aucun_filtre(tmp_path):
    """Le corollaire : l'attribuer a une demande serait une trace fabriquee."""
    chemin = tmp_path / "ancien.db"
    journal = JournalDesActions(db_path=str(chemin))
    journal.enregistrer(ActionEnregistree(
        outil="script", action="run", cible="local", resultat="SUCCESS"))

    assert len(journal.dernieres()) == 1
    assert journal.dernieres(requete_id="n-importe-quoi") == []


class TestStatistiquesDeRoutage:
    """`/api/models/statistics` — ce que chaque type de tache a donne."""

    def test_la_route_exige_la_cle(self, client):
        assert client.get("/api/models/statistics").status_code == 401

    def test_une_mesure_vide_repond_sans_pretendre_que_tout_va_bien(self, client, entetes):
        rendu = client.get("/api/models/statistics", headers=entetes).json()

        assert rendu["passages_totaux"] >= 0
        assert rendu["types_mesures"] >= 0
        assert "proprietaire" in rendu["qualite"], (
            "la reponse doit nommer la seule source honnete d'un score de qualite"
        )

    def test_la_route_ne_rend_jamais_de_qualite_chiffree(self, client, entetes):
        rendu = client.get("/api/models/statistics", headers=entetes).json()

        for bloc in rendu["par_type_de_tache"].values():
            assert bloc["qualite"] is None


class TestLeTypeDeTacheEstPoseSurLeVraiChemin:
    """Le type de tache doit etre pose par `dispatch_request`, pas par le test.

    **Ces tests existent parce qu'un sabotage les a reclames (13/09/2026) :**
    retirer `with tache(intent)` de `dispatch_request` laissait 35 tests au
    vert. Les tests de statistiques posaient le type eux-memes
    (`with tache(...)`), donc ils mesuraient leur propre mise en scene et pas
    le cablage. Ceux-ci passent par la fonction reelle.
    """

    @pytest.fixture
    def espion(self, monkeypatch):
        """Remplace le corps de l'aiguillage par un temoin du type de tache.

        C'est `_aiguiller` qui est double, pas `dispatch_request` : ce qu'on
        veut mesurer est precisement ce que `dispatch_request` fait AVANT de
        l'appeler.
        """
        from apps.backend.routers import chat as routeur_chat
        from core.observabilite.fil import type_tache_courant

        vus = []

        async def _temoin(request, intent):
            vus.append(type_tache_courant())
            return {"response": "ok", "agent": "TestAgent"}

        monkeypatch.setattr(routeur_chat, "_aiguiller", _temoin)
        return vus

    def _demande(self):
        from apps.backend.routers.chat import ChatRequest

        return ChatRequest(prompt="pose deux cloisons")

    def test_l_intention_fournie_devient_le_type_de_tache(self, espion):
        import asyncio

        from apps.backend.routers.chat import dispatch_request

        asyncio.run(dispatch_request(self._demande(), intent="PLAQUISTE"))

        assert espion == ["PLAQUISTE"]

    def test_l_intention_calculee_devient_le_type_de_tache(self, espion, monkeypatch):
        """Quand l'appelant n'en fournit pas, c'est celle du classement."""
        import asyncio

        from apps.backend.routers import chat as routeur_chat

        async def _classer(_prompt):
            return "CODE_EXECUTION"

        monkeypatch.setattr(routeur_chat.orchestrator, "analyze_intent", _classer)
        asyncio.run(routeur_chat.dispatch_request(self._demande()))

        assert espion == ["CODE_EXECUTION"]

    def test_le_type_de_tache_est_rendu_a_la_sortie(self, espion):
        """Il ne doit pas fuir sur l'appel suivant, qui aurait une autre intention."""
        import asyncio

        from apps.backend.routers.chat import dispatch_request
        from core.observabilite.fil import type_tache_courant

        asyncio.run(dispatch_request(self._demande(), intent="PLAQUISTE"))

        assert type_tache_courant() is None
