from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class ModelProvider(ABC):
    """Classe de base abstraite pour tous les fournisseurs de modeles."""
    
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Genere une reponse textuelle."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Verifie la disponibilite du service."""
        pass