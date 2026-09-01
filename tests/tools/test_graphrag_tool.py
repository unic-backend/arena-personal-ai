"""Le moteur de graphe dit ce qui ne va pas, il ne récite pas une phrase rassurante.

Défaut mesuré le 01/09/2026 sur cette machine : Docker éteint, `query_global`
rendait `status: "info"` et « Espace de connaissances prêt. Ajoutez vos
documents dans data/rag/graphrag_workspace/input. » — une phrase confiante,
fausse, avec un remède qui n'aurait rien changé. Le propriétaire aurait déposé
des documents pendant que le démon dormait.

C'est le défaut n° 2 de l'audit du même jour, dans un autre fichier :
`docker run` rend un code de sortie non nul **sans lever**, donc le chemin
d'exception n'est jamais pris et l'échec se déguise en autre chose.
"""
import subprocess

import pytest

from tools.rag import graphrag_tool as module
from tools.rag.graphrag_tool import IMAGE_GRAPHRAG, GraphRAGTool


@pytest.fixture
def espace(tmp_path):
    """Un espace de travail à lui, jamais celui du propriétaire."""
    return GraphRAGTool(workspace_dir=str(tmp_path / "graphrag"))


@pytest.fixture
def avec_un_document(espace):
    espace.add_document("note.txt", "Chantier de Fann Hock, 30 m2 de cloison.")
    return espace


class TestChaqueCauseEstNommee:

    def test_un_demon_eteint_est_dit_comme_tel(self, espace, monkeypatch):
        monkeypatch.setattr(module, "demon_repond", lambda: False)

        resultat = espace.query_global("mes themes ?")

        assert resultat["status"] == "error"
        assert "Docker" in resultat["response"]
        assert "prêt" not in resultat["response"], (
            "c'est exactement la phrase fausse que ce test empêche"
        )

    def test_une_image_absente_donne_la_commande_de_construction(
            self, espace, monkeypatch):
        monkeypatch.setattr(module, "demon_repond", lambda: True)
        monkeypatch.setattr(module, "image_construite", lambda _image: False)

        resultat = espace.query_global("mes themes ?")

        assert resultat["status"] == "error"
        assert IMAGE_GRAPHRAG in resultat["response"]
        assert "docker build" in resultat["response"]

    def test_un_espace_vide_est_la_seule_reponse_qui_parle_de_documents(
            self, espace, monkeypatch):
        monkeypatch.setattr(module, "demon_repond", lambda: True)
        monkeypatch.setattr(module, "image_construite", lambda _image: True)

        resultat = espace.query_global("mes themes ?")

        assert resultat["status"] == "info"
        assert str(espace.input_dir) in resultat["response"]

    def test_une_requete_en_echec_rend_sa_sortie_d_erreur(
            self, avec_un_document, monkeypatch):
        """Inventer une explication ferait perdre la seule trace exploitable."""
        monkeypatch.setattr(module, "demon_repond", lambda: True)
        monkeypatch.setattr(module, "image_construite", lambda _image: True)
        monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:
                            subprocess.CompletedProcess([], 1, "", "Traceback: index absent"))

        resultat = avec_un_document.query_global("mes themes ?")

        assert resultat["status"] == "error"
        assert "index absent" in resultat["response"]

    def test_une_requete_muette_n_est_pas_un_succes(
            self, avec_un_document, monkeypatch):
        monkeypatch.setattr(module, "demon_repond", lambda: True)
        monkeypatch.setattr(module, "image_construite", lambda _image: True)
        monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:
                            subprocess.CompletedProcess([], 0, "   \n", ""))

        assert avec_un_document.query_global("mes themes ?")["status"] == "error"

    def test_une_vraie_reponse_reste_un_succes(
            self, avec_un_document, monkeypatch):
        monkeypatch.setattr(module, "demon_repond", lambda: True)
        monkeypatch.setattr(module, "image_construite", lambda _image: True)
        monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:
                            subprocess.CompletedProcess([], 0, "Trois themes ressortent.", ""))

        resultat = avec_un_document.query_global("mes themes ?")

        assert resultat["status"] == "success"
        assert resultat["response"] == "Trois themes ressortent."


class TestAdresseOllamaVueDuConteneur:
    """Le port vient de la configuration ; seul l'hôte est propre à Docker."""

    def test_le_port_configure_est_conserve(self, monkeypatch):
        monkeypatch.setattr(module, "OLLAMA_URL", "http://127.0.0.1:11500")

        assert module._ollama_vu_du_conteneur() == "http://host.docker.internal:11500"

    def test_une_adresse_sans_port_retombe_sur_le_port_par_defaut(self, monkeypatch):
        monkeypatch.setattr(module, "OLLAMA_URL", "http://ollama-local")

        assert module._ollama_vu_du_conteneur() == "http://host.docker.internal:11434"
