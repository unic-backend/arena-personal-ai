"""L'agent de montage : de la phrase du proprietaire a la timeline validee.

C'est la piece que la mission OpenCut appelle *« the AI can translate
natural-language video requests into deterministic editing operations »*.
Elle relie trois choses qui existaient deja et ne se parlaient pas :

    la phrase  ->  le modele  ->  `core/montage/planificateur.py`
               ->  le connecteur `montage`  ->  la timeline, puis le rendu

**Ce que cet agent ne fait pas**, et qui est le sujet :

- Il **n'invente aucun plan**. Ollama eteint, JSON illisible, plan refuse :
  il le dit (`NOT_CONFIGURED` ou une erreur nommee). Aucune coupe par
  defaut, aucune timeline vide qui rendrait un fichier noir.
- Il **n'ouvre aucun fichier de lui-meme**. Le modele choisit parmi
  l'inventaire que l'appelant lui donne ; le planificateur substitue les
  chemins. Un nom hors inventaire est refuse.
- Il **ne rend rien sans confirmation**. `rendre` est une ecriture : elle
  passe par le registre, donc par la file d'attente, comme un devis PDF.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.montage.planificateur import (
    PlanRefuse,
    extraire_json,
    inventaire_depuis,
    prompt_de_planification,
    valider_plan,
)

logger = logging.getLogger("usman.agent.montage")

CONNECTEUR = "montage"

#: Format par defaut : le vertical des reseaux, ou vont les videos de chantier.
LARGEUR_PAR_DEFAUT, HAUTEUR_PAR_DEFAUT = 1080, 1920


class MontageAgent(BaseAgent):
    """Traduit une demande de montage en operations, puis les fait executer."""

    def __init__(
        self,
        provider: ModelProvider,
        memory: Optional[MemoryManager] = None,
        registre: Any = None,
    ):
        super().__init__(
            name="MontageAgent",
            description="Agent de montage video : plan de montage depuis une phrase, puis rendu verifie.",
            provider=provider,
            memory=memory,
        )
        self.registre = registre

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        contexte = context or {}
        chemins: List[str] = list(contexte.get("medias") or [])
        inventaire = inventaire_depuis(chemins)

        if not inventaire:
            return self._erreur(
                "Je n'ai aucun media a monter. Donne-moi les fichiers (video, "
                "photo, son) et je batis la timeline."
                + (f" Aucun des {len(chemins)} chemin(s) fournis n'existe."
                   if chemins else "")
            )

        if self.registre is None:
            return self._erreur(
                "Le connecteur de montage n'est pas branche sur cet agent : "
                "je ne peux valider aucune timeline."
            )

        if not await self.provider.is_available():
            return {
                "status": "warning",
                "agent": self.name,
                "response": (
                    "Je sais monter, mais Ollama ne repond pas. Demarre-le "
                    "(`ollama serve`) : je ne fabrique pas un plan de montage "
                    "sans le modele."
                ),
                "medias_disponibles": sorted(inventaire),
            }

        prompt = prompt_de_planification(
            demande=user_input,
            inventaire=inventaire,
            largeur=int(contexte.get("largeur") or LARGEUR_PAR_DEFAUT),
            hauteur=int(contexte.get("hauteur") or HAUTEUR_PAR_DEFAUT),
        )

        try:
            brut = await self.provider.generate(prompt=prompt)
        except Exception as erreur:  # httpx, timeout, modele absent
            logger.warning("Le modele n'a pas rendu de plan : %s", erreur)
            return self._erreur(f"Je n'ai pas pu joindre le modele : {erreur}")

        try:
            operations, refus = valider_plan(extraire_json(brut), inventaire)
        except PlanRefuse as erreur:
            # Le plan du modele est une DONNEE : refuse, il ne devient pas un
            # plan de repli. On rend la raison, pas une video approximative.
            logger.info("Plan de montage refuse : %s", erreur)
            return self._erreur(f"Le plan propose ne tient pas : {erreur}")

        return self._composer(operations, refus, inventaire)

    def _composer(
        self,
        operations: List[Dict[str, Any]],
        refus: List[str],
        inventaire: Dict[str, str],
    ) -> Dict[str, Any]:
        """Fait batir la timeline pour de vrai — la seule preuve qui vaille.

        Un plan « valide » qui ne compose pas n'est pas un plan. La
        composition ne rend aucun fichier : elle est libre, et c'est elle qui
        dit si les pistes, les durees et les chevauchements tiennent.
        """
        resultat = self.registre.executer(CONNECTEUR, "composer", operations=operations)
        # `PARTIAL` : la timeline tient, mais une partie du plan est tombee.
        # Ce n'est ni un echec (il y a un projet) ni un succes (il est
        # incomplet) — et l'annoncer `success` etait le defaut repare le
        # 01/09/2026.
        if resultat.statut.value not in ("SUCCESS", "PARTIAL"):
            return self._erreur(
                f"La timeline n'a pas tenu : {resultat.message}",
                operations=operations, refus=refus)

        erreurs = list(resultat.detail.get("erreurs") or []) + refus
        message = resultat.message
        if erreurs:
            message += "\n\nLignes ecartees :\n" + "\n".join(f"- {e}" for e in erreurs)

        return {
            "status": "warning" if erreurs else "success",
            "agent": self.name,
            "response": message,
            "operations": operations,
            "projet": resultat.detail.get("projet"),
            "medias_disponibles": sorted(inventaire),
            "lignes_ecartees": erreurs,
        }

    def _erreur(self, message: str, **detail: Any) -> Dict[str, Any]:
        return {"status": "error", "agent": self.name, "response": message, **detail}
