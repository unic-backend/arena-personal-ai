"""Agent de publication : il prepare le post, le connecteur dit ce qui est parti.

Cet agent portait, en plus de son travail, une copie du controle de permission
et de la journalisation. Depuis que `core/connectors/base.py` les garantit pour
tout connecteur, les garder ici les dedoublerait — deux endroits ou verifier la
meme chose, donc un endroit ou l'oublier.

Il lui reste ce qui est vraiment le sien :

1. verifier qu'il y a une video ;
2. faire rediger le post — c'est le « prepare tout, demande avant d'envoyer » ;
3. transmettre au connecteur et rendre sa reponse, quelle qu'elle soit.

Le brouillon est produit **dans tous les cas**, meme quand la publication est
refusee : preparer sans envoyer est le travail utile.
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.actions.journal import ActionEnregistree, JournalDesActions
from core.actions.resultat import ResultatAction, echec
from core.agent.base_agent import BaseAgent
from core.connectors.registre import RegistreConnecteurs
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("usman.agent.publisher")

# Le connecteur et la capacite vises. L'agent ne connait plus ni le service ni
# l'action de la politique : c'est le connecteur qui les declare.
CONNECTEUR = "tiktok"
CAPACITE = "publish_video"

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
        registre: Optional[RegistreConnecteurs] = None,
    ):
        super().__init__(
            name="PublisherAgent",
            description="Agent de publication multi-plateformes.",
            provider=provider,
            memory=memory
        )
        # Injectes plutot que fabriques : un test doit pouvoir observer ce qui
        # est journalise et fournir son propre connecteur.
        self.registre = registre or RegistreConnecteurs()
        self.journal = journal

    async def _brouillon(self, sujet: str) -> str:
        """Fait rediger le post. Sans modele disponible, on le dit au lieu d'inventer."""
        try:
            texte = await self.provider.generate(prompt=GABARIT_BROUILLON.format(sujet=sujet))
            return texte.strip()
        except Exception as erreur:
            logger.warning("Brouillon impossible : %s", erreur)
            return "(brouillon indisponible : le modele n'a pas repondu)"

    def _sortie(self, resultat: ResultatAction, brouillon: str = "") -> Dict[str, Any]:
        """Met le resultat a la forme attendue par l'aiguilleur, brouillon compris."""
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
        # Ce chemin n'atteint pas le connecteur, donc c'est ici qu'il se journalise.
        if not video_path or not Path(video_path).exists():
            manquant = echec(
                action=CAPACITE, cible=CONNECTEUR,
                message="Aucune video trouvee pour la publication.",
                fichier=str(video_path or ""),
            )
            if self.journal is not None:
                self.journal.enregistrer(ActionEnregistree.depuis_resultat(
                    manquant, outil=CONNECTEUR,
                    parametres={"fichier": str(video_path or "")},
                ))
            return self._sortie(manquant)

        brouillon = await self._brouillon(user_input)

        # Le connecteur verifie la permission, mesure sa sante, applique son
        # quota et journalise. L'agent ne refait aucun de ces gestes.
        resultat = self.registre.executer(
            CONNECTEUR, CAPACITE, compte=compte,
            fichier=str(video_path), legende=brouillon,
        )
        return self._sortie(resultat, brouillon)
