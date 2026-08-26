from abc import ABC, abstractmethod
from typing import Any, Dict


class SocialConnector(ABC):
    """Classe de base pour tous les connecteurs de réseaux sociaux (TikTok, YouTube, Insta)."""

    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.is_authenticated = False

    @abstractmethod
    def authenticate(self) -> bool:
        """Méthode pour s'authentifier (OAuth ou API Key)."""
        pass

    @abstractmethod
    def publish_video(self, video_path: str, title: str, description: str, tags: list) -> Dict[str, Any]:
        """Méthode pour publier une vidéo."""
        pass
