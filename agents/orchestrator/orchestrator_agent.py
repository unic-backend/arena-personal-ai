import logging
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("arena.agent.orchestrator")

# Liste fermée : toute réponse du modèle hors de cet ensemble est rejetée.
INTENTIONS = {
    "CHAT",
    "CODE_EXECUTION",
    "FRESH_INFO",
    "DEEP_REASONING",
    "DEEP_RESEARCH",
    "TREND_SEARCH",
    "VIDEO_ANALYSIS",
}

PROMPT_CLASSIFICATION = """Tu es un classifieur d'intention. Tu ne réponds jamais à la demande.
Choisis UNE seule étiquette parmi cette liste, et réponds UNIQUEMENT par cette étiquette :

CHAT            : conversation, question générale, explication, avis.
FRESH_INFO      : question dont la réponse a pu changer récemment — actualité,
                  dernière version d'un logiciel, prix, résultat, qui occupe un poste,
                  météo, cours, événement en cours. Tout ce qui demande de vérifier.
CODE_EXECUTION  : écrire ou exécuter du code, un script, un programme.
DEEP_REASONING  : résoudre un problème mathématique ou une démonstration.
DEEP_RESEARCH   : produire une étude, un rapport documenté, une recherche approfondie.
TREND_SEARCH    : chercher des tendances ou des idées de contenu vidéo.
VIDEO_ANALYSIS  : analyser, découper ou reformater un fichier vidéo.

Attention : parler DE code, DE maths ou D'une erreur n'est pas demander d'en produire.
« Explique-moi le code de la route » est CHAT, pas CODE_EXECUTION.
Une question sur un fait qui peut avoir change depuis est FRESH_INFO, pas CHAT :
« Quelle est la derniere version de Python ? » demande de verifier, pas de se souvenir.

Demande : {demande}

Étiquette :"""

class OrchestratorAgent(BaseAgent):
    """Agent principal de décision et de routage universel."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None):
        super().__init__(
            name="OrchestratorAgent",
            description="Agent principal de décision et de routage des tâches.",
            provider=provider,
            memory=memory
        )

    async def analyze_intent(self, user_input: str) -> str:
        """Détermine vers quel agent envoyer la demande.

        Le modèle rapide tranche (~200 ms). S'il est indisponible ou répond
        autre chose qu'une étiquette connue, on retombe sur les mots-clés — un
        repli moins fin, mais annoncé dans les journaux plutôt que silencieux.
        """
        intention = await self._classer_par_modele(user_input)
        if intention is not None:
            return intention

        logger.warning("Classification par le modèle indisponible : repli sur les mots-clés.")
        return self._classer_par_mots_cles(user_input)

    async def _classer_par_modele(self, user_input: str) -> Optional[str]:
        """Interroge le modèle rapide. Renvoie None si sa réponse n'est pas exploitable."""
        try:
            brut = await self.provider.generate(
                prompt=PROMPT_CLASSIFICATION.format(demande=user_input)
            )
        except Exception as e:
            logger.warning(f"Le modèle n'a pas pu classer la demande : {e}")
            return None

        # Le modèle bavarde parfois : on ne garde que le premier mot en majuscules
        # qui appartient à la liste fermée. Rien d'autre n'est accepté.
        for mot in brut.replace("\n", " ").replace("*", " ").replace("`", " ").split():
            candidat = mot.strip(".,:;!?\"'").upper()
            if candidat in INTENTIONS:
                return candidat

        logger.warning(f"Réponse de classification inexploitable : {brut[:80]!r}")
        return None

    def _classer_par_mots_cles(self, user_input: str) -> str:
        """Repli hors ligne : aiguillage par mots-clés, instantané mais approximatif."""
        text = user_input.lower()

        # Information fraiche : la reponse a pu changer depuis l'entrainement du modele.
        fresh_keywords = [
            "dernière version", "derniere version", "dernier modèle", "dernier modele",
            "aujourd'hui", "en ce moment", "actuellement", "actualité", "actualite",
            "cette semaine", "ce mois-ci", "cette année", "cette annee",
            "prix actuel", "cours de", "météo", "meteo", "qui est le président",
            "qui est le president", "quoi de neuf", "dernières nouvelles",
            "dernieres nouvelles", "récemment", "recemment",
        ]
        if any(k in text for k in fresh_keywords):
            return "FRESH_INFO"

        # Trend Search UNIQUEMENT si demande explicite de vidéo/tendances
        if "idée de vidéo" in text or "tendance tiktok" in text or "sujet chaud" in text or "stratégie vidéo" in text:
            return "TREND_SEARCH"

        # Raisonnement profond & Maths complexes
        reasoning_keywords = ["équation", "equation", "résous", "resous", "matrice", "intégrale", "dérivée", "démontre", "démontrer", "calcul complexe", "preuve"]
        if any(k in text for k in reasoning_keywords):
            return "DEEP_REASONING"

        # Code & Programmation
        code_keywords = ["code", "python", "script", "fonction", "programme", "calcule", "factorielle", "fibonacci", "algorithme", "bug", "erreur", "écris un"]
        if any(k in text for k in code_keywords):
            return "CODE_EXECUTION"

        # Recherche Profonde
        research_keywords = ["étude complète", "rapport détaillé", "recherche approfondie", "étude de marché", "dossier complet"]
        if any(k in text for k in research_keywords):
            return "DEEP_RESEARCH"

        # Vidéo
        video_keywords = ["découpe cette vidéo", "reformatte en 9:16", "sous-titre cette vidéo"]
        if any(k in text for k in video_keywords):
            return "VIDEO_ANALYSIS"

        return "CHAT"

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session_id = context.get("session_id", "default") if context else "default"
        owner_name = self.memory.get_fact("owner") if self.memory else "Saer"

        # La classification coûte un appel au modèle : si l'appelant l'a déjà
        # faite, on la réutilise au lieu de la refaire.
        intent = (context or {}).get("intent") or await self.analyze_intent(user_input)

        history = self.memory.get_recent_history(session_id=session_id, limit=6) if self.memory else []

        # PROMPT MONDIAL SANS BIAIS LOCAL FORCÉ
        system_prompt = (
            f"Tu es ARENA, une intelligence artificielle internationale de haut niveau, au service de {owner_name}.\n"
            f"Contexte temporel : Nous sommes en 2026.\n"
            f"Règles strictes :\n"
            f"1. Réponds STRICTEMENT et DIRECTEMENT à la question posée sans dériver vers d'autres sujets.\n"
            f"2. Ne parle du Sénégal QUE si la question concerne explicitement le Sénégal.\n"
            f"3. Pour les événements futurs (ex: Coupe du Monde 2026), rappelle poliment que l'événement n'a pas encore eu lieu et donne les faits historiques connus si pertinents.\n"
            f"4. Réponds en français fluide, naturel et professionnel."
        )

        prompt_lines = []
        for msg in history:
            role_label = owner_name if msg["role"] == "user" else "ARENA"
            prompt_lines.append(f"{role_label}: {msg['content']}")
        prompt_lines.append(f"{owner_name}: {user_input}")
        prompt_lines.append("ARENA:")

        reply = await self.provider.generate(prompt="\n".join(prompt_lines), system_prompt=system_prompt)
        return {
            "intent": intent,
            "agent": self.name,
            "response": reply.strip()
        }
