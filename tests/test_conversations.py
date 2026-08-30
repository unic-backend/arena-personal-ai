"""Le coffre a conversations, et ce qu'il doit garantir.

Le proprietaire voyait sur son telephone des conversations absentes de son PC :
elles vivaient dans le `localStorage` de chaque navigateur, donc nulle part en
commun. Ce module est le magasin partage. Ce qui doit rester vrai :

- la plus recente gagne, et **jamais** l'inverse ;
- une suppression se propage, au lieu que la conversation ressuscite au
  prochain envoi de l'appareil qui n'etait pas la ;
- une conversation trop grosse est refusee **en le disant**, et n'emporte pas
  le lot avec elle.
"""
import os
import tempfile

import pytest

from core.conversations.depot import DepotConversations


@pytest.fixture
def depot():
    return DepotConversations(db_path=os.path.join(tempfile.mkdtemp(), "conv.db"))


def conversation(identifiant, date, titre="Titre", messages=None):
    return {"id": identifiant, "updatedAt": date, "title": titre,
            "messages": messages or [], "createdAt": 1}


class TestArbitrageParLaDate:
    def test_une_conversation_est_conservee(self, depot):
        depot.deposer([conversation("a", 100)])
        assert [c["id"] for c in depot.lister()] == ["a"]

    def test_la_plus_recente_ecrase_l_ancienne(self, depot):
        depot.deposer([conversation("a", 100, titre="Ancien")])
        ecrites, _ = depot.deposer([conversation("a", 200, titre="Neuf")])

        assert ecrites == 1
        assert depot.lister()[0]["title"] == "Neuf"

    def test_une_version_plus_ancienne_n_ecrase_jamais(self, depot):
        """Le PC endormi ne doit pas ecraser ce que le telephone vient d'ecrire."""
        depot.deposer([conversation("a", 200, titre="Neuf")])
        ecrites, _ = depot.deposer([conversation("a", 100, titre="Ancien")])

        assert ecrites == 0
        assert depot.lister()[0]["title"] == "Neuf"

    def test_une_conversation_sans_date_n_ecrase_rien(self, depot):
        """Sans date, la conversation existe — mais elle ne gagne aucun arbitrage.

        Lui donner la date du jour la ferait gagner a tous les coups, ce qui est
        exactement ce que l'arbitrage doit empecher.
        """
        depot.deposer([conversation("a", 200, titre="Datee")])
        depot.deposer([{"id": "a", "title": "Sans date"}])

        assert depot.lister()[0]["title"] == "Datee"


class TestSuppression:
    def test_une_suppression_se_propage(self, depot):
        depot.deposer([conversation("a", 100)])
        assert depot.supprimer("a", 200) is True

        rendu = depot.lister()
        assert rendu == [{"id": "a", "supprimee": True, "updatedAt": 200}]
        assert depot.compter() == 0

    def test_une_conversation_supprimee_ne_ressuscite_pas(self, depot):
        """L'appareil absent au moment de la suppression la renvoie : c'est le cas."""
        depot.deposer([conversation("a", 100)])
        depot.supprimer("a", 200)

        ecrites, _ = depot.deposer([conversation("a", 100)])

        assert ecrites == 0
        assert depot.compter() == 0

    def test_une_ecriture_plus_recente_annule_la_suppression(self, depot):
        """Ecrire apres avoir supprime la reprend : la date reste l'arbitre."""
        depot.supprimer("a", 100)
        depot.deposer([conversation("a", 200, titre="Reprise")])

        assert depot.compter() == 1
        assert depot.lister()[0]["title"] == "Reprise"


class TestRefus:
    def test_une_conversation_trop_grosse_est_refusee_en_le_disant(self):
        petit = DepotConversations(
            db_path=os.path.join(tempfile.mkdtemp(), "c.db"), taille_max=200
        )
        enorme = conversation("gros", 100, titre="x" * 500)

        ecrites, refusees = petit.deposer([enorme])

        assert ecrites == 0
        assert refusees == ["gros"]
        assert petit.compter() == 0

    def test_une_refusee_n_emporte_pas_les_autres(self):
        """Perdre le lot entier pour une seule ligne serait pire que la refuser."""
        petit = DepotConversations(
            db_path=os.path.join(tempfile.mkdtemp(), "c.db"), taille_max=200
        )
        ecrites, refusees = petit.deposer([
            conversation("gros", 100, titre="x" * 500),
            conversation("petit", 100),
        ])

        assert ecrites == 1
        assert refusees == ["gros"]
        assert [c["id"] for c in petit.lister()] == ["petit"]

    def test_une_conversation_sans_identifiant_est_refusee(self, depot):
        ecrites, refusees = depot.deposer([{"updatedAt": 100, "title": "orpheline"}])

        assert ecrites == 0
        assert refusees == ["(sans identifiant)"]


class TestFormeConservee:
    def test_les_champs_inconnus_du_serveur_survivent(self, depot):
        """Le serveur est un coffre, pas un modele : il ne rabote rien.

        L'interface ajoute des champs souvent (variantes, pieces jointes...).
        Un serveur qui ne garderait que ce qu'il connait les perdrait en
        silence, et la synchronisation deviendrait une perte de donnees.
        """
        riche = conversation("a", 100)
        riche["variants"] = [{"id": "v1", "text": "essai"}]
        riche["champInvente"] = {"profond": [1, 2, 3]}

        depot.deposer([riche])

        assert depot.lister()[0] == riche

    def test_une_ligne_illisible_est_ignoree_pas_rendue_a_moitie(self, depot):
        """Une conversation tronquee ressemble a une conversation : elle ment."""
        depot.deposer([conversation("bonne", 100)])
        import sqlite3
        with sqlite3.connect(depot.db_path) as conn:
            conn.execute(
                "INSERT INTO conversations (id, updated_at, supprimee, contenu)"
                " VALUES ('cassee', 200, 0, '{ceci n est pas du json')"
            )

        rendu = depot.lister()

        assert [c["id"] for c in rendu] == ["bonne"]


class TestPersistance:
    def test_le_contenu_survit_a_une_reouverture(self):
        """Le disque Railway est la raison d'etre de ce magasin."""
        chemin = os.path.join(tempfile.mkdtemp(), "conv.db")
        DepotConversations(db_path=chemin).deposer([conversation("a", 100)])

        relu = DepotConversations(db_path=chemin)

        assert [c["id"] for c in relu.lister()] == ["a"]


class TestLesRoutes:
    """La passerelle : meme cle, meme limiteur que le reste."""

    @pytest.fixture
    def client(self, monkeypatch, depot):
        from fastapi.testclient import TestClient

        from apps.backend import security
        from apps.backend.routers import conversations as routeur
        monkeypatch.setattr(security, "USMAN_API_KEY", "cle-de-test")
        monkeypatch.setattr(routeur, "depot_conversations", depot)
        from apps.backend.main import app
        return TestClient(app)

    def test_sans_cle_la_lecture_est_refusee(self, client):
        assert client.get("/conversations").status_code == 401

    def test_un_appareil_envoie_et_recoit_la_verite_fusionnee(self, client):
        client.post("/conversations/sync", headers={"Authorization": "Bearer cle-de-test"},
                    json={"conversations": [conversation("pc", 100, titre="Du PC")]})

        reponse = client.post(
            "/conversations/sync", headers={"Authorization": "Bearer cle-de-test"},
            json={"conversations": [conversation("tel", 200, titre="Du telephone")]},
        )

        corps = reponse.json()
        assert reponse.status_code == 200
        # Le telephone recoit AUSSI la conversation du PC : c'est tout l'objet.
        assert sorted(c["id"] for c in corps["conversations"]) == ["pc", "tel"]
        assert corps["ecrites"] == 1
        assert corps["refusees"] == []

    def test_la_lecture_rend_ce_qui_a_ete_depose(self, client):
        client.post("/conversations/sync", headers={"Authorization": "Bearer cle-de-test"},
                    json={"conversations": [conversation("a", 100)]})

        corps = client.get("/conversations",
                           headers={"Authorization": "Bearer cle-de-test"}).json()

        assert [c["id"] for c in corps["conversations"]] == ["a"]
        assert corps["total"] == 1
