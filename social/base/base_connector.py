"""Base commune aux connecteurs de reseaux sociaux.

Le cadre general des connecteurs (capacites, sante, quotas, journal) est prevu
au chapitre 4 du VOLET ARENA OS. Ce qui change ici, et qui ne peut pas attendre :
**une methode qui n'atteint aucun service ne renvoie pas un dictionnaire libre
ou elle peut ecrire ce qu'elle veut.** Elle renvoie un `ResultatAction`, dont le
statut ne peut pas mentir sur ce qui a eu lieu.
"""
from abc import ABC, abstractmethod

from core.actions.resultat import ResultatAction


class SocialConnector(ABC):
    """Classe de base pour tous les connecteurs de reseaux sociaux."""

    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.is_authenticated = False

    @abstractmethod
    def authenticate(self) -> bool:
        """S'authentifie aupres de la plateforme.

        Renvoie False tant qu'aucune authentification reelle n'a abouti. Un
        connecteur sans identifiants renvoie False — jamais True « en mode
        hors-ligne ».
        """

    @abstractmethod
    def publish_video(self, video_path: str, title: str, description: str, tags: list) -> ResultatAction:
        """Publie une video, ou dit precisement pourquoi elle ne l'a pas ete."""
