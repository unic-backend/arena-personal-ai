"""Configuration du chat autonome, sans connexion ni ecriture a l'import."""
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from apps.backend.config import BASE_DIR, DB_PATH, MODE_IA, MODELE_CONVERSATION, OLLAMA_URL


class AutonomousSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    db_path: Path = DB_PATH
    chroma_path: Path = BASE_DIR / "chroma_db"
    openai_key: str = Field(default="", repr=False)
    model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    local_embedding_model: str = "bge-m3"
    local_url: str = OLLAMA_URL
    local_model: str = MODELE_CONVERSATION
    mode: str = MODE_IA
    tavily_key: str = Field(default="", repr=False)
    iterations: int = Field(default=5, ge=1, le=5)
    timeout: float = Field(default=30, gt=0, le=120)
    context_chars: int = Field(default=24000, ge=16000, le=100000)
    history_messages: int = Field(default=20, ge=2, le=100)
    worker_interval: float = Field(default=5, gt=0, le=60)

    # Conversation intelligence: precision is intentionally favoured over recall.
    memory_rerank_top_k: int = Field(default=6, ge=0, le=20)
    memory_lexical_weight: float = Field(default=0.35, ge=0, le=1)
    memory_entity_weight: float = Field(default=0.30, ge=0, le=1)
    memory_topic_weight: float = Field(default=0.25, ge=0, le=1)
    memory_recency_weight: float = Field(default=0.10, ge=0, le=1)
    memory_relevance_threshold: float = Field(default=0.22, ge=0, le=1)
    memory_debug: bool = False

    @classmethod
    def from_env(cls) -> "AutonomousSettings":
        return cls(
            chroma_path=Path(os.getenv("USMAN_CHROMA_PATH", str(BASE_DIR / "chroma_db"))),
            openai_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("USMAN_AUTONOMOUS_MODEL", "gpt-4.1-mini"),
            local_embedding_model=os.getenv("EMBEDDINGS_LOCAL_MODEL", "bge-m3"),
            tavily_key=os.getenv("TAVILY_API_KEY", ""),
            timeout=float(os.getenv("USMAN_AUTONOMOUS_TIMEOUT", "30")),
            context_chars=int(os.getenv("USMAN_AUTONOMOUS_CONTEXT_CHARS", "24000")),
            history_messages=int(os.getenv("USMAN_HISTORY_MESSAGES", "20")),
            memory_rerank_top_k=int(os.getenv("USMAN_MEMORY_RERANK_TOP_K", "6")),
            memory_lexical_weight=float(os.getenv("USMAN_MEMORY_LEXICAL_WEIGHT", "0.35")),
            memory_entity_weight=float(os.getenv("USMAN_MEMORY_ENTITY_WEIGHT", "0.30")),
            memory_topic_weight=float(os.getenv("USMAN_MEMORY_TOPIC_WEIGHT", "0.25")),
            memory_recency_weight=float(os.getenv("USMAN_MEMORY_RECENCY_WEIGHT", "0.10")),
            memory_relevance_threshold=float(os.getenv("USMAN_MEMORY_RELEVANCE_THRESHOLD", "0.22")),
            memory_debug=os.getenv("USMAN_MEMORY_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"},
        )
