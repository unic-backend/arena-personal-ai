import logging
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.specialistes.selection import bloc_de_methode, choisir
from tools.coder.repo_engineer_tool import RepoEngineerTool

logger = logging.getLogger("usman.agent.repo_engineer")

class RepoEngineerAgent(BaseAgent):
    """Agent d'analyse d'architecture multi-fichiers (lecture seule).

    Il LIT la structure du depot et propose un plan. Il ne modifie aucun fichier.
    """

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
                 registre: Any = None):
        super().__init__(
            name="RepoEngineerAgent",
            description="Agent d'analyse d'architecture de dépôt, en lecture seule.",
            provider=provider,
            memory=memory
        )
        self.repo_tool = RepoEngineerTool()
        self.registre = registre

    def _regard_sur_le_depot(self) -> tuple[str, str]:
        """Ce que l'agent voit du dépôt, et **d'où ça vient**.

        **Défaut mesuré le 07/09/2026** (audit profond) : cet agent analysait
        une architecture avec 30 lignes d'arborescence tronquée, pendant que
        `gitingest` — enregistré, testé, diagnostiqué — n'était appelé par
        AUCUN chemin d'exécution. Un connecteur que rien n'atteint est mort,
        quelle que soit la qualité de son code (DEC-0061, DEC-0066).

        Le repli n'est pas un détail : `gitingest` est optionnel, et son
        absence ne doit jamais empêcher une analyse. La source est rendue
        avec le contenu pour que le prompt dise ce qu'il a réellement lu.
        """
        if self.registre is not None:
            # `delai` court : un « coup d'oeil » n'a pas besoin des 180 s par
            # defaut du connecteur — surtout que ce depot porte des moteurs
            # externes volumineux mais gitignores (`tools/vision/faceplugin/`),
            # que le parcours interne de gitingest doit quand meme traverser
            # avant de pouvoir les exclure. Le repli sur l'arborescence,
            # juste en dessous, reste rapide dans tous les cas — mesure le
            # 09/09/2026.
            resultat = self.registre.executer("gitingest", "ingerer", source=".", delai=20)
            if resultat.statut.value == "SUCCESS":
                resume = str(resultat.detail.get("resume") or "").strip()
                arbre = str(resultat.detail.get("arbre") or "").strip()
                vu = "\n\n".join(p for p in (resume, arbre) if p)
                if vu:
                    return vu[:8000], "gitingest"
            logger.info("gitingest indisponible (%s) : repli sur l'arborescence.",
                        resultat.statut.value)

        return "\n".join(self.repo_tool.get_tree(max_depth=2)[:30]), "arborescence"

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info(f"RepoEngineerAgent analyse la tâche projet : {user_input}")

        # 1. Inspection de la structure du dépôt
        tree_str, source_du_regard = self._regard_sur_le_depot()

        # Meme defaut que DEC-0061 (OpenViking) : une methode de specialiste
        # declaree pour REPO_ENGINEERING (`tests`, `architecture`,
        # `core/specialistes/catalogue.py`) n'atteignait jamais cet agent —
        # seul le repli conversationnel la composait, un chemin que
        # REPO_ENGINEERING ne prend jamais puisqu'il est deja aiguille ici.
        methode = bloc_de_methode(choisir(user_input, "REPO_ENGINEERING"))

        prompt = (
            "Tu es RepoEngineerAgent, un ingénieur logiciel principal d'élite (style Devin / Odysseus).\n"
            "Analyse le projet et la tâche suivante, puis propose un diagnostic d'architecture précis.\n\n"
            f"Ce que tu vois du dépôt (source : {source_du_regard}) :\n{tree_str}\n\n"
            f"Demande de modification / Ingénierie : {user_input}\n\n"
            "Diagnostic & Plan d'Ingénierie Multi-fichiers :"
            + (f"\n\n{methode}" if methode else "")
        )

        analysis = await self.provider.generate(prompt=prompt)

        return {
            "status": "success",
            "agent": self.name,
            "architecture_plan": analysis.strip(),
            "response": (
                "**Rapport d'ingenierie logicielle (RepoEngineerAgent)**\n\n"
                f"{analysis.strip()}\n\n"
                "---\n"
                "*Cet agent analyse et propose. Il ne modifie aucun fichier : "
                "c'est toi qui decides d'appliquer les changements ou non.*"
            )
        }
