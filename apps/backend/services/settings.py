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
    local_url: str = OLLAMA_URL
    local_model: str = MODELE_CONVERSATION
    mode: str = MODE_IA
    tavily_key: str = Field(default="", repr=False)
    iterations: int = Field(default=5, ge=1, le=5)
    timeout: float = Field(default=30, gt=0, le=120)
    context_chars: int = Field(default=24000, ge=16000, le=100000)
    history_messages: int = Field(default=20, ge=2, le=100)
    worker_interval: float = Field(default=5, gt=0, le=60)

    @classmethod
    def from_env(cls) -> "AutonomousSettings":
        return cls(
            chroma_path=Path(os.getenv("USMAN_CHROMA_PATH", str(BASE_DIR / "chroma_db"))),
            openai_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("USMAN_AUTONOMOUS_MODEL", "gpt-4.1-mini"),
            tavily_key=os.getenv("TAVILY_API_KEY", ""),
            timeout=float(os.getenv("USMAN_AUTONOMOUS_TIMEOUT", "30")),
            context_chars=int(os.getenv("USMAN_AUTONOMOUS_CONTEXT_CHARS", "24000")),
        )
