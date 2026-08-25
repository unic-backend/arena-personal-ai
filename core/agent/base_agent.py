from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from core.models.base import ModelProvider
from core.memory.memory_manager import MemoryManager

class BaseAgent(ABC):
    """Classe abstraite dont héritent tous les agents spécialisés d'ARENA."""
    
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