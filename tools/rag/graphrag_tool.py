import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from apps.backend.config import OLLAMA_URL
from tools.docker_local import demon_repond, image_construite

logger = logging.getLogger("usman.tools.graphrag")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GRAPHRAG_DIR = BASE_DIR / "data" / "rag" / "graphrag_workspace"
INPUT_DIR = GRAPHRAG_DIR / "input"

GRAPHRAG_DIR.mkdir(parents=True, exist_ok=True)
INPUT_DIR.mkdir(parents=True, exist_ok=True)

#: L'image qui porte Microsoft GraphRAG. Nommee ici parce que deux endroits
#: la citent : la sonde et la commande.
IMAGE_GRAPHRAG = "usman-graphrag"

#: Vue depuis un conteneur, la machine hote n'est pas `127.0.0.1`. On garde
#: donc le port configure, mais l'hote propre a Docker.
HOTE_DEPUIS_CONTENEUR = "host.docker.internal"


def _ollama_vu_du_conteneur() -> str:
    """L'adresse d'Ollama telle qu'un conteneur peut l'atteindre.

    Le port vient de la configuration (`OLLAMA_BASE_URL`) ; seul l'hote est
    remplace. Ecrire l'adresse entiere en dur ignorait un Ollama servi sur
    un autre port.
    """
    port = OLLAMA_URL.rsplit(":", 1)[-1]
    if not port.isdigit():
        return f"http://{HOTE_DEPUIS_CONTENEUR}:11434"
    return f"http://{HOTE_DEPUIS_CONTENEUR}:{port}"

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

    @staticmethod
    def _indisponible(raison: str, remede: str) -> Dict[str, Any]:
        """Une capacité absente se rapporte, elle ne se déguise pas.

        Jusqu'au 01/09/2026, TOUT code de sortie non nul rendait
        `status: "info"` et « Espace de connaissances prêt. Ajoutez vos
        documents… » — y compris un démon Docker éteint ou une image jamais
        construite. Mesuré sur cette machine : la phrase partait, confiante et
        fausse, avec un remède qui n'aurait rien changé.
        """
        logger.warning("Microsoft GraphRAG indisponible : %s", raison)
        return {
            "status": "error",
            "engine": "Microsoft GraphRAG",
            "response": f"Microsoft GraphRAG n'est pas disponible : {raison}\n\n{remede}",
        }

    def _documents_indexes(self) -> bool:
        """Y a-t-il seulement quelque chose à interroger ?

        La seule question dont « ajoutez vos documents » est la vraie réponse.
        """
        return any(self.input_dir.iterdir()) if self.input_dir.is_dir() else False

    def query_global(self, prompt: str) -> Dict[str, Any]:
        """Interroge le graphe de connaissances Microsoft GraphRAG (Recherche Globale).

        Chaque cause d'échec est nommée séparément : un démon éteint, une image
        absente et un espace vide n'appellent pas le même geste, et les
        confondre envoyait le propriétaire déposer des documents alors que
        Docker ne tournait pas.
        """
        logger.info(f"🔍 Requête Globale Microsoft GraphRAG : {prompt}")

        if not demon_repond():
            return self._indisponible(
                "le démon Docker est inactif.", "Démarre Docker Desktop.")

        if not image_construite(IMAGE_GRAPHRAG):
            return self._indisponible(
                f"l'image « {IMAGE_GRAPHRAG} » n'est pas construite.",
                f"docker build -t {IMAGE_GRAPHRAG} .")

        if not self._documents_indexes():
            return {
                "status": "info",
                "engine": "Microsoft GraphRAG",
                "response": (
                    "📊 [Microsoft GraphRAG] Espace de connaissances prêt, mais "
                    "vide.\n\nDépose tes documents dans "
                    f"{self.input_dir}, puis relance l'indexation."
                ),
            }

        try:
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{self.workspace_dir}:/app/workspace",
                "-e", f"GRAPHRAG_OLLAMA_HOST={_ollama_vu_du_conteneur()}",
                IMAGE_GRAPHRAG,
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
        except Exception as e:
            logger.error(f"Erreur requête Microsoft GraphRAG : {e}")
            return {
                "status": "error",
                "engine": "Microsoft GraphRAG",
                "response": f"❌ Microsoft GraphRAG : {str(e)}",
            }

        if res.returncode != 0:
            # Docker répond, l'image existe, les documents sont là : ce qui a
            # échoué est la requête elle-même. Sa sortie d'erreur est ce qui
            # reste diagnosticable — inventer une explication la ferait perdre.
            detail = (res.stderr or res.stdout or "").strip()[:500]
            return self._indisponible(
                f"la requête a échoué (code {res.returncode}).",
                detail or "Aucune sortie d'erreur.")

        reponse = res.stdout.strip()
        if not reponse:
            return self._indisponible(
                "la requête a abouti sans produire de texte.",
                "Vérifie que l'indexation a bien été lancée sur ces documents.")

        return {
            "status": "success",
            "engine": "Microsoft GraphRAG",
            "response": reponse,
        }

if __name__ == "__main__":
    tool = GraphRAGTool()
    print("🕸️ Outil Microsoft GraphRAGTool prêt dans tools/rag/graphrag_tool.py !")
