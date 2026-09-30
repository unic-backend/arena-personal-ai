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

    #: Comment l'agent se presente au registre (DEC-0145) : lu par la
    #: decouverte, jamais recopie dans une liste centrale.
    identifiant = "repo"
    competences = ('architecture de depot', 'analyse de code', 'plusieurs fichiers')

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

        1. Si codebase_memory (DeusData, DEC-0201) est déclaré et opérationnel,
           on extrait l'architecture et les relations structurelles.
        2. Sinon repli sur gitingest (DEC-0047).
        3. Sinon repli sur l'arborescence brute (repo_tool).
        """
        if self.registre is not None:
            if getattr(self.registre, "est_declare", lambda n: False)("codebase_memory"):
                res_cbm = self.registre.executer("codebase_memory", "architecture", chemin=".", delai=10)
                if res_cbm.statut.value == "SUCCESS":
                    arch = str(res_cbm.message or res_cbm.detail.get("donnees") or "").strip()
                    if arch:
                        return arch[:8000], "codebase_memory"

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

        analysis = await self.rediger(prompt=prompt)

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
