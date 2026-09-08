"""L'agent de generation d'interface : decrit -> genere -> valide -> artefact.

Composant restant de l'integration OpenUI (voir `core/production/
ui_generation.py` pour ce qui a ete verifie et ce qui a ete refuse). Cet
agent fait ce qu'un connecteur ne fait pas : appeler le modele. Le
connecteur (`core/connectors/ui_generate.py`, via le registre) fait ce que
cet agent ne fait pas : verifier les permissions et ecrire le fichier —
meme separation que Xaar Kaname/KrillinAI dans `agents/video/
production_agent.py`.

**Aucun code genere n'est jamais execute par ARENA.** Le fichier ecrit est
une page HTML (ou un composant texte) que le proprietaire ouvre lui-meme
dans SON navigateur, exactement comme n'importe quel autre artefact de
`media/rendered/` — jamais charge, importe ou execute par le processus
ARENA lui-meme.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.actions.resultat import Statut
from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.production.ui_generation import extraire_code, prompt_systeme, prompt_utilisateur

logger = logging.getLogger("usman.agent.ui_generation")


class UiGenerationAgent(BaseAgent):
    """Une description en langage naturel devient une interface reelle."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
                *, registre: Any = None) -> None:
        super().__init__(
            name="UiGenerationAgent",
            description="Genere une interface (HTML/React/Svelte/Web Component) a partir d'une description.",
            provider=provider, memory=memory)
        self.registre = registre

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        contexte = context or {}
        framework = str(contexte.get("framework") or "html").strip().lower()
        existant = contexte.get("existant")

        if self.registre is None:
            return self._erreur("aucun registre de connecteurs branche")
        if not await self.provider.is_available():
            return {
                "status": "warning", "agent": self.name,
                "response": ("Je sais generer une interface, mais le modele ne "
                            "repond pas. Demarre-le : je n'invente pas de code sans lui."),
            }

        prompt = prompt_systeme(framework) + "\n\n" + prompt_utilisateur(user_input, existant)
        try:
            reponse_brute = await self.provider.generate(prompt=prompt)
        except Exception as erreur:  # noqa: BLE001 — httpx, timeout, modele absent
            logger.warning("Le modele n'a pas repondu pour la generation d'interface : %s", erreur)
            return self._erreur(f"Je n'ai pas pu joindre le modele : {erreur}")

        code = extraire_code(reponse_brute)
        if code is None:
            return self._erreur(
                "Le modele n'a pas rendu de bloc de code lisible — rien n'a ete ecrit.")

        resultat = self.registre.executer(
            "ui_generate", "generer", code=code, framework=framework,
            titre=str(contexte.get("titre") or user_input[:60]))
        return self._depuis(resultat, "generer")

    def _depuis(self, resultat: Any, action: str) -> Dict[str, Any]:
        """Meme traduction que `agents/audio/audio_agent.py::_depuis` —
        reprise ici plutot qu'importee, pour que les deux agents restent
        independants l'un de l'autre."""
        statut = resultat.statut.value
        reponse: Dict[str, Any] = {"agent": self.name, "action": action, "response": resultat.message}
        if statut == "SUCCESS":
            reponse["status"] = "success"
            reponse["preuve"] = resultat.preuve
            reponse.update(resultat.detail)
        elif statut in ("NOT_CONFIGURED", Statut.A_CONFIRMER.value):
            reponse["status"] = "warning"
            reponse.update(resultat.detail)
        else:
            reponse["status"] = "error"
        return reponse

    def _erreur(self, message: str) -> Dict[str, Any]:
        return {"status": "error", "agent": self.name, "response": message}
