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
        self.collaborateurs = None

    async def demander_specialiste(
        self, specialiste: str, requete: str, contexte: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Delegue une sous-tache a un autre agent ARENA deja construit.

        La profondeur est bornee pour empecher A -> B -> A sans fin. Le
        registre est injecte par runtime; BaseAgent ne connait aucun agent
        concret et n'en reconstruit jamais.
        """
        if self.collaborateurs is None:
            return {"status": "error", "agent": self.name,
                    "response": "Aucun registre de collaborateurs branche."}
        if not self.collaborateurs.connait(specialiste):
            return {"status": "error", "agent": self.name,
                    "response": f"Specialiste inconnu: {specialiste}."}
        ctx = dict(contexte or {})
        profondeur = int(ctx.get("_delegation_depth") or 0)
        if profondeur >= 4:
            return {"status": "error", "agent": self.name,
                    "response": "Delegation arretee: profondeur maximale atteinte."}
        chaine = list(ctx.get("_delegation_chain") or [])
        if specialiste in chaine:
            return {"status": "error", "agent": self.name,
                    "response": "Delegation arretee: boucle detectee."}
        ctx["_delegation_depth"] = profondeur + 1
        ctx["_delegation_chain"] = chaine + [self.name]
        ctx["origine_agent"] = self.name
        return await self.collaborateurs.demander(specialiste, requete, ctx)

    @abstractmethod
    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Exécute la tâche principale de l'agent."""
        pass
