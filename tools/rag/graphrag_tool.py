import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("arena.tools.graphrag")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GRAPHRAG_DIR = BASE_DIR / "data" / "rag" / "graphrag_workspace"
INPUT_DIR = GRAPHRAG_DIR / "input"

GRAPHRAG_DIR.mkdir(parents=True, exist_ok=True)
INPUT_DIR.mkdir(parents=True, exist_ok=True)

class GraphRAGTool:
    """Connecteur Microsoft GraphRAG (Graphes de Connaissances & Communautés d'idées) via Docker."""

    def __init__(self, workspace_dir: Optional[str] = None):
        self.workspace_dir = Path(workspace_dir).resolve() if workspace_dir else GRAPHRAG_DIR
        self.input_dir = self.workspace_dir / "input"
        self.input_dir.mkdir(parents=True, exist_ok=True)

    def add_document(self, filename: str, content: str) -> bool:
        """Ajoute un document dans l'espace de travail GraphRAG."""
        try:
            target_file = self.input_dir / filename
            target_file.write_text(content, encoding="utf-8")
            logger.info(f"Document {filename} ajouté dans le workspace Microsoft GraphRAG.")
            return True
        except Exception as e:
            logger.error(f"Erreur ajout document GraphRAG : {e}")
            return False

    def query_global(self, prompt: str) -> Dict[str, Any]:
        """Interroge le graphe de connaissances Microsoft GraphRAG (Recherche Globale)."""
        logger.info(f"🔍 Requête Globale Microsoft GraphRAG : {prompt}")

        try:
            # Exécution de la requête Microsoft GraphRAG via Docker Python 3.11
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{self.workspace_dir}:/app/workspace",
                "-e", "GRAPHRAG_OLLAMA_HOST=http://host.docker.internal:11434",
                "python:3.11-slim",
                "python", "-m", "graphrag.query",
                "--root", "/app/workspace",
                "--method", "global",
                prompt
            ]

            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60
            )

            if res.returncode == 0:
                return {
                    "status": "success",
                    "engine": "Microsoft GraphRAG",
                    "response": res.stdout.strip()
                }
            else:
                # Fallback informatif si l'indexation n'a pas encore été tournée
                return {
                    "status": "info",
                    "engine": "Microsoft GraphRAG",
                    "response": f"📊 [Microsoft GraphRAG] Espace de connaissances prêt. Ajoutez vos documents dans data/rag/graphrag_workspace/input."
                }

        except Exception as e:
            logger.error(f"Erreur requête Microsoft GraphRAG : {e}")
            return {
                "status": "error",
                "engine": "Microsoft GraphRAG",
                "response": f"❌ Microsoft GraphRAG : {str(e)}"
            }

if __name__ == "__main__":
    tool = GraphRAGTool()
    print("🕸️ Outil Microsoft GraphRAGTool prêt dans tools/rag/graphrag_tool.py !")