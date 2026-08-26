import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.permissions.permission_manager import PermissionManager
from social.tiktok.tiktok_connector import TikTokConnector

logger = logging.getLogger("usman.agent.publisher")

class PublisherAgent(BaseAgent):
    """Agent chargé de publier les vidéos sur les réseaux sociaux."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="PublisherAgent",
            description="Agent de publication multi-plateformes.",
            provider=provider,
            memory=memory
        )
        self.permissions = PermissionManager()
        self.tiktok = TikTokConnector()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        video_path = context.get("video_path") if context else None

        if not video_path or not Path(video_path).exists():
            return {"status": "error", "agent": self.name, "response": "❌ Aucune vidéo trouvée pour la publication."}

        # VÉRIFICATION DE SÉCURITÉ (Règle 34)
        if not self.permissions.is_allowed("PUBLISH"):
            logger.warning("Publication bloquée par les permissions de sécurité.")

            # Si bloqué, on fait une simulation via l'IA pour générer le post
            prompt = f"Rédige un titre accrocheur, une courte description et 5 hashtags pour publier cette vidéo sur TikTok. Le sujet est : {user_input}"
            post_content = await self.provider.generate(prompt=prompt)

            self.tiktok.authenticate()
            sim_result = self.tiktok.publish_video(video_path, "Titre généré", "Description générée", ["#Simulation"])

            return {
                "status": "success",
                "agent": self.name,
                "response": f"🔒 MODE SÉCURITÉ ACTIF (Publication réelle bloquée).\n\n[SIMULATION TIKTOK] : {sim_result['message']}\n\n📝 Brouillon du post généré par l'IA :\n{post_content.strip()}"
            }

        # Code futur pour publication réelle...
        return {"status": "error", "response": "Publication réelle non implémentée."}
