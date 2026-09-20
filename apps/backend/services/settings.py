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

    # Conversation intelligence: precision avant rappel.
    recent_context_window: int = Field(default=8, ge=2, le=30)
    retrieval_top_k: int = Field(default=20, ge=4, le=50)
    rerank_top_k: int = Field(default=5, ge=1, le=12)
    relevance_threshold: float = Field(default=0.18, ge=0.0, le=1.0)
    semantic_weight: float = Field(default=0.34, ge=0.0, le=1.0)
    lexical_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    entity_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    topic_weight: float = Field(default=0.16, ge=0.0, le=1.0)
    recency_weight: float = Field(default=0.06, ge=0.0, le=1.0)
    conversation_weight: float = Field(default=0.04, ge=0.0, le=1.0)
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
            recent_context_window=int(os.getenv("USMAN_RECENT_CONTEXT_WINDOW", "8")),
            retrieval_top_k=int(os.getenv("USMAN_RETRIEVAL_TOP_K", "20")),
            rerank_top_k=int(os.getenv("USMAN_RERANK_TOP_K", "5")),
            relevance_threshold=float(os.getenv("USMAN_MEMORY_RELEVANCE_THRESHOLD", "0.18")),
            memory_debug=os.getenv("USMAN_MEMORY_DEBUG", "").strip().lower() in {"1", "true", "yes"},
        )
