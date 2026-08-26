"""Moteur documentaire LightRAG : exige Ollama et le modèle d'embeddings."""
import pytest

from tools.rag.lightrag_tool import LightRAGTool

DOCUMENT = (
    "Le projet ARENA est une IA autonome créée par Saer au Sénégal. Elle intègre des "
    "agents spécialisés pour le code, la recherche profonde et le montage vidéo 9:16."
)


@pytest.mark.integration
def test_un_document_insere_est_retrouve():
    outil = LightRAGTool()
    if not outil.insert_text(DOCUMENT):
        pytest.skip("LightRAG n'a pas pu indexer : dépendance ou modèle d'embeddings absent.")

    reponse = outil.query("Qui a créé le projet ARENA ?", mode="hybrid")

    assert "Saer" in reponse
