from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider


class BaseAgent(ABC):
    """Classe abstraite dont héritent tous les agents spécialisés d'Usman."""

    def __init__(
        self,
        name: str,
        description: str,
        provider: ModelProvider,
        memory: Optional[MemoryManager] = None
    ):
        self.name = name
        self.description = description
        self.provider = provider
        self.memory = memory

    @abstractmethod
    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Exécute la tâche principale de l'agent."""
        pass
