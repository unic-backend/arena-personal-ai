"""Agent de publication : il prepare le post, et il dit la verite sur l'envoi.

Le brouillon est un vrai travail et il est fait dans tous les cas — c'est le
« prepare tout, demande avant d'envoyer » de la specification. Ce qui a change
le 2026-08-27, c'est le statut rendu : l'agent renvoyait `success` quand la
permission etait bloquee **et** quand le connecteur ne faisait que simuler. Trois
situations differentes portaient le meme mot.

Elles en ont maintenant trois :

- permission `PUBLISH` bloquee  -> `DENIED`, brouillon fourni
- connecteur non branche        -> `NOT_CONFIGURED`, brouillon fourni
- publication reelle            -> n'existe pas encore, `NOT_IMPLEMENTED`

Aucun de ces trois chemins n'emet de requete. Le jour ou l'un le fera, il devra
rendre une preuve, sans quoi `ResultatAction` refusera de se construire.
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.actions.journal import ActionEnregistree, JournalDesActions
from core.actions.resultat import ResultatAction, a_confirmer, echec, refuse
from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.permissions.controle import ControleAcces
from social.tiktok.tiktok_connector import TikTokConnector

logger = logging.getLogger("usman.agent.publisher")

# Adresse de l'action dans la politique de permissions. Ecrite une fois, pour
# que le controle et le journal ne puissent pas designer deux choses.
SERVICE = "social"
# Deux noms, et ils ne sont pas interchangeables : `ACTION_POLITIQUE` est
# l'action telle que la politique la declare (`social.publish`) ; `ACTION` est
# ce qui est journalise, plus precis parce qu'un jour on publiera aussi autre
# chose qu'une video. Les confondre ferait chercher une regle « publish_video »
# qui n'existe pas — et la regle « action inconnue = refusee » repondrait DENIED
# avec l'origine « defaut », ce qui est vrai et incomprehensible.
ACTION_POLITIQUE = "publish"
ACTION = "publish_video"
CIBLE = "TikTok"

GABARIT_BROUILLON = (
    "Redige un titre accrocheur, une courte description et 5 hashtags pour "
    "publier cette video sur TikTok. Le sujet est : {sujet}"
)


class PublisherAgent(BaseAgent):
    """Prepare la publication d'une video et rend l'etat reel de l'envoi."""

    def __init__(
        self,
        provider: ModelProvider,
        memory: Optional[MemoryManager] = None,
        journal: Optional[JournalDesActions] = None,
        acces: Optional[ControleAcces] = None,
    ):
        super().__init__(
            name="PublisherAgent",
            description="Agent de publication multi-plateformes.",
            provider=provider,
            memory=memory
        )
        self.acces = acces or ControleAcces()
        # Conserve pour les appelants qui interrogeaient directement les neuf
        # booleens : c'est le meme objet, pas une copie.
        self.permissions = self.acces.permissions
        self.tiktok = TikTokConnector()
        # Injecte plutot que fabrique ici : un test doit pouvoir observer ce qui
        # est journalise, et un agent qui se cree son propre journal ne le permet
        # pas. `runtime.py` fournit celui de la plateforme.
        self.journal = journal

    async def _brouillon(self, sujet: str) -> str:
        """Fait rediger le post. Sans modele disponible, on le dit au lieu d'inventer."""
        try:
            texte = await self.provider.generate(prompt=GABARIT_BROUILLON.format(sujet=sujet))
            return texte.strip()
        except Exception as erreur:
            logger.warning("Brouillon impossible : %s", erreur)
            return "(brouillon indisponible : le modele n'a pas repondu)"

    def _journaliser(self, resultat: ResultatAction, video_path: Optional[str]) -> None:
        """Ecrit l'action au journal. Un journal absent ou en panne n'arrete rien."""
        if self.journal is None:
            return
        self.journal.enregistrer(ActionEnregistree.depuis_resultat(
            resultat,
            outil="tiktok",
            parametres={"fichier": str(video_path or "")},
            niveau_permission="PUBLISH",
        ))

    def _sortie(
        self, resultat: ResultatAction, brouillon: str = "", video_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Met le resultat a la forme attendue par l'aiguilleur, et le journalise."""
        self._journaliser(resultat, video_path)
        corps = resultat.to_dict()
        corps["agent"] = self.name
        if brouillon:
            corps["brouillon"] = brouillon
            corps["response"] = f"{resultat.message}\n\nBrouillon du post :\n{brouillon}"
        return corps

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        video_path = context.get("video_path") if context else None
        compte = context.get("compte") if context else None

        # Sans fichier, rien a preparer : on s'arrete avant d'appeler le modele.
        if not video_path or not Path(video_path).exists():
            return self._sortie(echec(
                action=ACTION,
                cible=CIBLE,
                message="Aucune video trouvee pour la publication.",
                fichier=str(video_path or ""),
            ), video_path=video_path)

        brouillon = await self._brouillon(user_input)

        autorisation = self.acces.verifier(SERVICE, ACTION_POLITIQUE, compte=compte)

        if autorisation.refuse:
            logger.warning("Publication refusee (%s).", autorisation.origine)
            return self._sortie(
                refuse(action=ACTION, cible=CIBLE, permission=autorisation.origine),
                brouillon,
                video_path=video_path,
            )

        if autorisation.demande_confirmation:
            # Tout est pret ; il manque le « oui ». Le mecanisme de confirmation
            # lui-meme est le chapitre 5 : d'ici la, l'agent dit ou il en est au
            # lieu de publier sans accord ou de faire comme s'il avait refuse.
            return self._sortie(
                a_confirmer(
                    action=ACTION, cible=CIBLE,
                    message=f"Pret a publier sur {CIBLE}. Risque {autorisation.risque.value}. "
                            f"Rien n'est parti : dis-moi si je publie.",
                    risque=autorisation.risque.value,
                ),
                brouillon,
                video_path=video_path,
            )

        # Autorise sans rien demander : c'est le connecteur qui decide, et
        # aujourd'hui il n'est pas branche. Il le declare lui-meme.
        return self._sortie(
            self.tiktok.publish_video(video_path, "", brouillon, []), brouillon, video_path
        )
