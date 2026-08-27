"""Connecteur TikTok — declare son absence de configuration, ne la simule pas.

Etat au 2026-08-27 : **aucune integration TikTok n'existe dans ARENA.** Il n'y a
ni application declaree, ni jeton OAuth, ni appel a l'API Content Posting.

Ce fichier renvoyait auparavant `status: "success"` et le message « simulee
comme publiee avec succes ». Le champ `simulated: True` etait bien present, mais
le statut — le seul champ qu'un appelant teste — affirmait une publication qui
n'avait pas eu lieu. C'est ce que la specification du proprietaire interdit
explicitement (section 27), et c'est le defaut qui se serait propage a chaque
connecteur ecrit sur ce modele.

Ce qu'il faut pour que ce connecteur devienne reel, et que le proprietaire seul
peut fournir : une application TikTok for Developers approuvee, le scope
`video.publish`, et un jeton OAuth stocke hors du code source.
"""
import logging

from core.actions.resultat import ResultatAction, non_configure
from social.base.base_connector import SocialConnector

logger = logging.getLogger("usman.social.tiktok")

# Ce qui manque, dit une seule fois, pour que le message et la documentation ne
# puissent pas diverger.
CE_QUI_MANQUE = (
    "une application TikTok for Developers approuvee, le scope video.publish, "
    "et un jeton OAuth hors du code source"
)


class TikTokConnector(SocialConnector):
    """Connecteur TikTok non configure. Il n'emet aucune requete."""

    def __init__(self) -> None:
        super().__init__("TikTok")

    def authenticate(self) -> bool:
        """Renvoie toujours False : il n'y a aucun identifiant a presenter."""
        logger.info("TikTok non configure : aucune authentification possible.")
        self.is_authenticated = False
        return False

    def publish_video(
        self, video_path: str, title: str, description: str, tags: list
    ) -> ResultatAction:
        """Ne publie rien et le declare. Aucune requete ne sort d'ici."""
        logger.warning("Publication TikTok demandee alors que le connecteur n'est pas configure.")
        return non_configure(
            action="publish_video",
            cible=self.platform_name,
            ce_qui_manque=CE_QUI_MANQUE,
            titre=title,
            fichier=video_path,
        )
