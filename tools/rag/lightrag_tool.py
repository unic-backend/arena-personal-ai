import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("arena.tools.rag")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAG_STORAGE_DIR = BASE_DIR / "data" / "rag" / "storage"
RAG_RAW_DIR = BASE_DIR / "data" / "rag" / "raw"

RAG_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
RAG_RAW_DIR.mkdir(parents=True, exist_ok=True)

class LightRAGTool:
    """Connecteur RAG documentaire local-first basé sur LightRAG + Ollama."""

    def __init__(self, working_dir: Optional[str] = None):
        self.working_dir = Path(working_dir).resolve() if working_dir else RAG_STORAGE_DIR
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self.rag = None

    def _init_rag(self):
        """Initialise LightRAG avec le moteur local Ollama."""
        if self.rag is not None:
            return

        try:
            from lightrag import LightRAG
            from lightrag.llm.ollama import ollama_embed, ollama_model_complete
            from lightrag.utils import EmbeddingFunc

            # Configuration 100% locale avec Ollama (qwen2.5-coder:14b / qwen3.5:9b)
            self.rag = LightRAG(
                working_dir=str(self.working_dir),
                llm_model_func=ollama_model_complete,
                llm_model_name="qwen2.5-coder:14b",
                llm_model_max_async=4,
                llm_model_kwargs={"host": "http://127.0.0.1:11434", "options": {"num_ctx": 4096}},
                embedding_func=EmbeddingFunc(
                    embedding_dim=768,
                    max_token_size=8192,
                    func=lambda texts: ollama_embed(
                        texts,
                        embed_model="nomic-embed-text",
                        host="http://127.0.0.1:11434"
                    )
                )
            )
            logger.info("LightRAG initialisé avec succès en mode local Ollama.")
        except Exception as e:
            logger.error(f"Erreur initialisation LightRAG : {e}")
            raise e

    def insert_text(self, text_content: str) -> bool:
        """Ajoute un texte ou document dans la base de connaissances LightRAG."""
        try:
            self._init_rag()
            self.rag.insert(text_content)
            logger.info("Texte inséré avec succès dans LightRAG.")
            return True
        except Exception as e:
            logger.error(f"Erreur insertion LightRAG : {e}")
            return False

    def query(self, prompt: str, mode: str = "hybrid") -> str:
        """
        Interroge la base documentaire LightRAG.
        Modes disponibles: 'hybrid', 'local', 'global', 'naive'
        """
        try:
            self._init_rag()
            from lightrag import QueryParam

            result = self.rag.query(
                prompt,
                param=QueryParam(mode=mode)
            )
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.error(f"Erreur requête LightRAG : {e}")
            return f"❌ Erreur de recherche documentaire LightRAG : {str(e)}"

if __name__ == "__main__":
    tool = LightRAGTool()
    print("📚 Module LightRAGTool prêt dans tools/rag/lightrag_tool.py !")
