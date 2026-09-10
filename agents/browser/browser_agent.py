import logging
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.connectors.registre import RegistreConnecteurs
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.security.trust import TrustLevel, wrap

logger = logging.getLogger("usman.agent.browser")

class BrowserAgent(BaseAgent):
    """Agent autonome de navigation Web active (Playwright + Browser-Use).

    Jusqu'au 06/09/2026, cet agent appelait `BrowserUseTool` en direct —
    la seule capacité d'ARENA qui agit sur le web de façon autonome
    (clics, formulaires) sans passer par le contrôle d'accès
    (`ControleAcces`/`config/permissions_services.yaml`) que WanGP
    ou KrillinAI respectent déjà. Corrigé (DEC-0059) : la navigation passe
    désormais par `registre.executer("browser", "naviguer", ...)`, comme
    `VisionAgent` le fait déjà pour `securite_chantier` — même discipline,
    jamais un second système de permissions.

    Audit Fuji-Web (docs/audits/fuji_web_audit.md) : le texte d'une page web
    est une DONNÉE, jamais une consigne (mission §13) — le résultat de
    `browser_use`, qui a réellement lu des pages tierces, est enveloppé
    (`TrustLevel.EXTERNAL`) avant d'entrer dans la réponse, comme
    `FreshInfoAgent`/`TrendAnalyzerAgent`/`FinanceAgent` le font déjà pour
    tout contenu externe. Avant cette mission, ce texte arrivait BRUT dans
    la réponse — un défaut trouvé en lisant le code, pas supposé.
    """

    def __init__(
        self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
        registre: Optional[RegistreConnecteurs] = None,
    ):
        super().__init__(
            name="BrowserAgent",
            description="Agent autonome de pilotage du navigateur Web (clics, formulaires, scraping dynamique).",
            provider=provider,
            memory=memory
        )
        self.registre = registre

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info(f"BrowserAgent au travail sur la tâche : {user_input}")

        if self.registre is None:
            return {
                "status": "error",
                "agent": self.name,
                "response": "❌ Aucun registre de connecteurs branché : la navigation ne peut pas être autorisée.",
            }

        contexte = context or {}
        parametres: Dict[str, Any] = {"tache": user_input}
        # Optionnels, jamais devines : un appelant qui ne les fournit pas
        # obtient exactement le comportement d'avant ces parametres.
        for cle in ("max_steps", "fichiers_autorises", "sensitive_data", "allowed_domains"):
            if contexte.get(cle) is not None:
                parametres[cle] = contexte[cle]

        resultat = self.registre.executer("browser", "naviguer", **parametres)
        corps = resultat.to_dict() if hasattr(resultat, "to_dict") else dict(resultat or {})
        statut = corps.get("statut", corps.get("status"))
        detail = corps.get("detail") or {}

        if statut in ("SUCCESS", "PARTIAL"):
            # Ce que browser_use a lu sur des pages tierces est une DONNEE,
            # jamais une consigne — enveloppe avant d'entrer dans la reponse.
            resultat_enveloppe = wrap(
                str(detail.get("resultat") or corps.get("message") or ""),
                TrustLevel.EXTERNAL, f"navigation:{detail.get('moteur') or 'inconnu'}",
            ).text
            prefixe = "✅ **Navigation Web Autonome Accomplie**" if statut == "SUCCESS" \
                else "⚠️ **Navigation partiellement aboutie, non entièrement vérifiée**"
            return {
                "status": "success",
                "agent": self.name,
                "moteur": detail.get("moteur"),
                "verification": detail.get("verification"),
                "nombre_etapes": detail.get("nombre_etapes"),
                "response": (
                    f"🌐 {prefixe}\n\n**Tâche :** {user_input}"
                    f"\n\n**Résultat :**\n{resultat_enveloppe}"),
            }
        if statut == "NEEDS_CONFIRMATION":
            return {
                "status": "success",
                "agent": self.name,
                "response": f"🌐 {corps.get('message') or 'Navigation en attente de confirmation.'}",
            }
        return {
            "status": "error",
            "agent": self.name,
            "verification": detail.get("verification"),
            "response": f"❌ Échec de la navigation Web autonome : {corps.get('message') or 'Erreur inconnue'}",
        }
