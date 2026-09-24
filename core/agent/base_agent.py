import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from core.agent.execution_policy import delegation_autorisee, politique_pour
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider


# Un specialiste distant/local peut se bloquer (modele, outil, reseau). Une
# collaboration ne doit jamais immobiliser l'agent appelant sans limite.
DELAI_SPECIALISTE_SECONDES = 45.0


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
        chaine = list(ctx.get("_delegation_chain") or [])
        # La requete originale fixe le budget une seule fois. Un sous-agent ne
        # peut pas augmenter son propre budget en reformulant sa sous-tache.
        politique = politique_pour(str(ctx.get("_requete_racine") or requete))
        if not delegation_autorisee(politique, chaine, specialiste):
            return {"status": "error", "agent": self.name,
                    "response": "Delegation arretee: boucle ou budget atteint."}
        ctx["_requete_racine"] = str(ctx.get("_requete_racine") or requete)
        ctx["_delegation_depth"] = profondeur + 1
        ctx["_delegation_chain"] = chaine + [self.name]
        ctx["origine_agent"] = self.name
        try:
            return await asyncio.wait_for(
                self.collaborateurs.demander(specialiste, requete, ctx),
                timeout=DELAI_SPECIALISTE_SECONDES,
            )
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "agent": self.name,
                "specialiste": specialiste,
                "response": (
                    f"Le specialiste {specialiste} n'a pas repondu dans le delai. "
                    "La demande principale peut continuer sans lui."
                ),
            }
        except Exception as erreur:  # noqa: BLE001
            return {
                "status": "error",
                "agent": self.name,
                "specialiste": specialiste,
                "response": f"Le specialiste {specialiste} est indisponible: {type(erreur).__name__}.",
            }

    @abstractmethod
    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Exécute la tâche principale de l'agent."""
        pass
