import logging
from typing import Dict, Any
from social.base.base_connector import SocialConnector

logger = logging.getLogger("arena.social.tiktok")

class TikTokConnector(SocialConnector):
    def __init__(self):
        super().__init__("TikTok")

    def authenticate(self) -> bool:
        logger.info("[SIMULATION] Authentification TikTok réussie (Mode Hors-Ligne).")
        self.is_authenticated = True
        return True

    def publish_video(self, video_path: str, title: str, description: str, tags: list) -> Dict[str, Any]:
        logger.info(f"[SIMULATION] Préparation publication sur TikTok : {title}")
        return {
            "status": "success",
            "platform": self.platform_name,
            "simulated": True,
            "message": f"Vidéo '{title}' simulée comme publiée avec succès sur TikTok avec les hashtags {tags}."
        }