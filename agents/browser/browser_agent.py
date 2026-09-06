import logging
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.connectors.registre import RegistreConnecteurs
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("usman.agent.browser")

class BrowserAgent(BaseAgent):
    """Agent autonome de navigation Web active (Playwright + Browser-Use).

    Jusqu'au 06/09/2026, cet agent appelait `BrowserUseTool` en direct —
    la seule capacité d'ARENA qui agit sur le web de façon autonome
    (clics, formulaires) sans passer par le contrôle d'accès
    (`ControleAcces`/`config/permissions_services.yaml`) que WanGP
    ou KrillinAI respectent déjà. Corrigé (DEC-0059) : la navigation passe
    désormais par `registre.executer("browser", "naviguer", ...)`, comme
    `VisionAgent` le fait déjà pour `securite_chantier` — même discipline,
    jamais un second système de permissions.
    """

    def __init__(
        self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
        registre: Optional[RegistreConnecteurs] = None,
    ):
        super().__init__(
            name="BrowserAgent",
            description="Agent autonome de pilotage du navigateur Web (clics, formulaires, scraping dynamique).",
            provider=provider,
            memory=memory
        )
        self.registre = registre

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info(f"BrowserAgent au travail sur la tâche : {user_input}")

        if self.registre is None:
            return {
                "status": "error",
                "agent": self.name,
                "response": "❌ Aucun registre de connecteurs branché : la navigation ne peut pas être autorisée.",
            }

        resultat = self.registre.executer("browser", "naviguer", tache=user_input)
        corps = resultat.to_dict() if hasattr(resultat, "to_dict") else dict(resultat or {})
        statut = corps.get("statut", corps.get("status"))

        if statut == "SUCCESS":
            detail = corps.get("detail") or {}
            return {
                "status": "success",
                "agent": self.name,
                "moteur": detail.get("moteur"),
                "response": (
                    f"🌐 **Navigation Web Autonome Accomplie !**\n\n**Tâche :** {user_input}"
                    f"\n\n**Résultat :**\n{detail.get('resultat') or corps.get('message')}"),
            }
        if statut == "NEEDS_CONFIRMATION":
            return {
                "status": "success",
                "agent": self.name,
                "response": f"🌐 {corps.get('message') or 'Navigation en attente de confirmation.'}",
            }
        return {
            "status": "error",
            "agent": self.name,
            "response": f"❌ Échec de la navigation Web autonome : {corps.get('message') or 'Erreur inconnue'}",
        }
