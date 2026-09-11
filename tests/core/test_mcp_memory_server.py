"""core/mcp/memory_server.py — le premier serveur MCP d'ARENA.

Mission ARENA x AI MEMORY VAULT (DEC-0090). Deux niveaux de preuve :

1. Les outils appeles directement (rapide) — verifie la LOGIQUE.
2. Un vrai sous-processus, parle par le vrai protocole JSON-RPC stdio via
   `core/mcp/stdio_transport.py::ClientMcpStdio` (le meme client qu'ARENA
   utilise deja pour OpenTakeoff) — verifie que le serveur repond
   REELLEMENT au protocole, pas seulement que ses fonctions Python marchent
   isolement.
"""
import importlib
import os
import sys

import pytest

from core.mcp.stdio_transport import ClientMcpStdio


@pytest.fixture
def serveur(tmp_path, monkeypatch):
    """Reimporte le module avec une base fraiche, isolee par test."""
    chemin = str(tmp_path / "memoire.db")
    monkeypatch.setenv("USMAN_MEMORY_DB_PATH", chemin)
    monkeypatch.delenv("USMAN_MEMORY_VAULT_PASSPHRASE", raising=False)
    import core.mcp.memory_server as module
    importlib.reload(module)
    yield module
    module._memoire = None


class TestOutilsEnDirect:
    def test_create_memory_ecrit_toujours_une_inference(self, serveur):
        resultat = serveur.create_memory(contenu="Le proprietaire prefere le sombre.",
                                          type="semantic", source="mcp-test")
        assert resultat["nature"] == "INFERENCE"
        assert resultat["etat"] == "ACTIVE"

    def test_create_memory_type_inconnu_est_refuse(self, serveur):
        with pytest.raises(ValueError):
            serveur.create_memory(contenu="x", type="pas-un-type-valide")

    def test_list_memory_rend_ce_qui_a_ete_cree(self, serveur):
        serveur.create_memory(contenu="a", type="semantic")
        serveur.create_memory(contenu="b", type="semantic")
        assert len(serveur.list_memory()) == 2

    def test_search_memory_ne_rend_que_le_pertinent(self, serveur):
        serveur.create_memory(contenu="Le tarif pose BA13 est 5000 F/m2.", type="semantic")
        serveur.create_memory(contenu="Le client s'appelle Moussa.", type="semantic")
        resultats = serveur.search_memory(query="tarif BA13")
        assert any("tarif" in r["contenu"].lower() for r in resultats)

    def test_approve_memory_promeut_en_fait(self, serveur):
        cree = serveur.create_memory(contenu="x", type="semantic")
        approuve = serveur.approve_memory(id=cree["id"], source="proprietaire")
        assert approuve["nature"] == "FACT"

    def test_approve_memory_id_inconnu_leve(self, serveur):
        with pytest.raises(ValueError):
            serveur.approve_memory(id="inconnu", source="x")

    def test_reject_memory_exclut_de_list_memory_par_defaut(self, serveur):
        cree = serveur.create_memory(contenu="faux", type="semantic")
        serveur.reject_memory(id=cree["id"], source="proprietaire : faux")
        assert len(serveur.list_memory()) == 0
        assert len(serveur.list_memory(inclure_rejetes=True)) == 1

    def test_delete_memory_supprime_reellement(self, serveur):
        cree = serveur.create_memory(contenu="x", type="semantic")
        resultat = serveur.delete_memory(id=cree["id"])
        assert resultat["status"] == "deleted"
        assert len(serveur.list_memory()) == 0

    def test_delete_memory_id_inconnu_leve(self, serveur):
        with pytest.raises(ValueError):
            serveur.delete_memory(id="inconnu")

    def test_list_memory_respecte_le_projet(self, serveur):
        serveur.create_memory(contenu="a", type="semantic", projet="chantier-a")
        serveur.create_memory(contenu="b", type="semantic", projet="chantier-b")
        assert len(serveur.list_memory(projet="chantier-a")) == 1


class TestProtocoleReelViaSousProcessus:
    """Ces deux tests lancent REELLEMENT `python -m core.mcp.memory_server`
    et lui parlent en JSON-RPC sur stdio — le meme genre de preuve que le
    restart test d'un connecteur (DEC-0085/0087) : un client MCP externe
    (Claude Desktop, Cursor) parlerait exactement ce protocole."""

    def test_deux_appels_en_sequence_via_le_vrai_protocole(self, tmp_path):
        chemin = str(tmp_path / "memoire.db")
        env = dict(os.environ)
        env["USMAN_MEMORY_DB_PATH"] = chemin
        env.pop("USMAN_MEMORY_VAULT_PASSPHRASE", None)

        with ClientMcpStdio([sys.executable, "-u", "-m", "core.mcp.memory_server"],
                             dossier=os.getcwd(), delai=20.0, environnement=env) as client:
            r1 = client.appeler("create_memory", {"contenu": "premier", "type": "semantic"})
            assert r1.ok, r1.raison
            r2 = client.appeler("create_memory", {"contenu": "second", "type": "semantic"})
            assert r2.ok, r2.raison

            r3 = client.appeler("list_memory", {})
            assert r3.ok, r3.raison
            liste = r3.resultat["structuredContent"]["result"]
            assert len(liste) == 2

    def test_la_liste_des_outils_correspond_exactement_aux_six_attendus(self, tmp_path):
        chemin = str(tmp_path / "memoire.db")
        env = dict(os.environ)
        env["USMAN_MEMORY_DB_PATH"] = chemin

        with ClientMcpStdio([sys.executable, "-u", "-m", "core.mcp.memory_server"],
                             dossier=os.getcwd(), delai=20.0, environnement=env) as client:
            reponse = client.outils()
            assert reponse.ok, reponse.raison
            noms = {outil["name"] for outil in reponse.resultat["tools"]}
            assert noms == {
                "search_memory", "create_memory", "list_memory",
                "approve_memory", "reject_memory", "delete_memory",
            }
