"""Connecteur TikTok — declare son absence de configuration, ne la simule pas.

Etat au 2026-08-27 : **aucune integration TikTok n'existe dans ARENA.** Il n'y a
ni application declaree, ni jeton OAuth, ni appel a l'API Content Posting.

Ce fichier renvoyait auparavant `status: "success"` et le message « simulee
comme publiee avec succes ». Le champ `simulated: True` etait bien present, mais
le statut — le seul champ qu'un appelant teste — affirmait une publication qui
n'avait pas eu lieu.

Il repose desormais sur `core/connectors/base.py`, qui rend cette erreur
impossible a refaire : la capacite est declaree, la sante est **mesuree**, la
permission passe avant tout, et une implementation qui pretend reussir sans
preuve ne peut pas construire son resultat.

Ce qu'il faut pour que ce connecteur devienne reel, et que le proprietaire seul
peut fournir : une application TikTok for Developers approuvee, le scope
`video.publish`, et un jeton OAuth stocke hors du code source.
"""
import logging
import os
from typing import Any, Dict

from core.actions.resultat import ResultatAction, non_configure
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante

logger = logging.getLogger("usman.social.tiktok")

# Ce qui manque, dit une seule fois, pour que le message, la sante et la
# documentation ne puissent pas diverger.
CE_QUI_MANQUE = (
    "une application TikTok for Developers approuvee, le scope video.publish, "
    "et un jeton OAuth hors du code source"
)

# Variable d'environnement qui porterait le jeton. Elle n'existe pas aujourd'hui,
# et la sonde le constate au lieu de le supposer.
VARIABLE_JETON = "TIKTOK_ACCESS_TOKEN"

# Plafond de l'API Content Posting. Declare des maintenant : un quota decouvert
# le jour ou le compte est suspendu coute plus cher qu'un quota ecrit d'avance.
QUOTA_PUBLICATIONS_PAR_MINUTE = 2


class TikTokConnector(Connecteur):
    """Connecteur TikTok. Sans jeton, il ne tente rien et le dit."""

    service = "social"
    nom = "tiktok"

    def capacites(self) -> Dict[str, Capacite]:
        """Une seule capacite declaree. Le reste n'existe pas, donc n'est pas la."""
        return {
            "publish_video": Capacite(
                nom="publish_video",
                action="publish",
                description="Publie une video sur TikTok avec sa legende.",
                ecriture=True,
                quota_par_minute=QUOTA_PUBLICATIONS_PAR_MINUTE,
            ),
        }

    def sonder(self) -> Sante:
        """Mesure : le jeton est-il present ? Aucune requete n'est emise sans lui.

        La sonde ne dit pas « operationnel » parce qu'un fichier existe : elle
        constate l'absence du seul element sans lequel rien ne peut partir.
        """
        if not os.getenv(VARIABLE_JETON):
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="TikTok n'est pas connecte : aucun jeton d'acces.",
                ce_qui_manque=CE_QUI_MANQUE,
            )
        # Un jeton present ne prouve pas qu'il soit valide. Tant que l'appel de
        # verification n'est pas ecrit, l'etat reste INCONNU — et INCONNU ne vaut
        # jamais OPERATIONNEL, donc rien ne partira.
        return Sante(
            etat=EtatSante.INCONNU,
            message=f"{VARIABLE_JETON} est presente, mais aucune verification "
                    f"aupres de TikTok n'est implementee.",
        )

    def authentifier(self) -> bool:
        """Renvoie toujours False : il n'y a aucun echange OAuth implemente."""
        logger.info("TikTok non configure : aucune authentification possible.")
        return False

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        """N'est jamais atteint aujourd'hui : la sonde arrete avant.

        Ce corps existe pour que le chemin reel ait une place ou etre ecrit. Il
        declare son absence plutot que de rendre un resultat plausible.
        """
        logger.warning("Publication TikTok demandee alors que rien n'est implemente.")
        return non_configure(
            action=capacite.nom,
            cible=self.nom,
            ce_qui_manque=CE_QUI_MANQUE,
            fichier=str(parametres.get("fichier", "")),
        )
