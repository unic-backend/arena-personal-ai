import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from tools.coder.swe_aci_tool import SWEACITool

logger = logging.getLogger("arena.agent.swe")

# Mots d'instruction courants : ils ne servent a rien pour chercher dans le code.
MOTS_VIDES = {
    "corrige", "corriger", "repare", "reparer", "réparer", "analyse", "analyser",
    "trouve", "trouver", "cherche", "chercher", "explique", "expliquer", "regarde",
    "montre", "montrer", "comment", "pourquoi", "quelle", "quel", "quels", "quelles",
    "dans", "pour", "avec", "cette", "celui", "peux", "peut", "faire", "verifie",
    "probleme", "problème", "erreur", "bogue", "merci", "stp", "svp",
}

MOTIF_FICHIER = re.compile(r"[\w.-]+\.(?:py|html|yaml|yml|json|md|txt)")
MOTIF_NETTOYAGE = re.compile(r"[^\w-]")


class SWEAgent(BaseAgent):
    """Agent d'analyse chirurgicale de bugs (protocole ACI, Princeton NLP).

    Il LIT le depot et propose une correction. Il ne modifie aucun fichier.
    """

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="SWEAgent",
            description="Agent d'analyse de bugs en lecture seule (protocole ACI).",
            provider=provider,
            memory=memory
        )
        self.aci = SWEACITool()

    def _extraire_terme(self, texte: str) -> str:
        """Choisit le mot le plus pertinent a rechercher dans le depot."""
        if not texte:
            return "def"

        #
        #  1) Un nom de fichier cite est toujours la meilleure piste.
        fichiers = MOTIF_FICHIER.findall(texte)
        if fichiers:
            return Path(fichiers[0]).name

        # 2) Sinon : le mot le plus long qui ne soit pas un simple mot d'instruction.
        mots = [MOTIF_NETTOYAGE.sub("", m) for m in texte.split()]
        candidats = [m for m in mots if len(m) >= 4 and m.lower() not in MOTS_VIDES]
        if candidats:
            return max(candidats, key=len)

        return "def"

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        terme = self._extraire_terme(user_input)
        logger.info(f"SWEAgent analyse le probleme (terme recherche : '{terme}')")

        search_res = self.aci.search_dir(terme)

        prompt = (
            "Tu es SWEAgent, un ingenieur logiciel d'elite utilisant le protocole ACI (Princeton NLP).\n"
            "Analyse ce probleme de code et les occurrences trouvees dans le depot, "
            "puis propose la correction chirurgicale exacte (fichier, lignes, code de remplacement).\n\n"
            f"Occurrences ACI trouvees (recherche sur '{terme}') :\n{search_res}\n\n"
            f"Probleme a resoudre : {user_input}\n\n"
            "Analyse chirurgicale & plan de correction :"
        )

        analysis = await self.provider.generate(prompt=prompt)

        return {
            "status": "success",
            "agent": self.name,
            "search_term": terme,
            "search_matches": search_res,
            "response": (
                "**Analyse chirurgicale ACI (SWEAgent)**\n\n"
                f"*Terme recherche dans le depot : `{terme}`*\n\n"
                f"{analysis.strip()}\n\n"
                "---\n"
                "*Cet agent analyse et propose. Il ne modifie aucun fichier : "
                "c'est toi qui decides d'appliquer la correction ou non.*"
            )
        }
