import datetime
import logging
import re
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("usman.agent.orchestrator")

# Liste fermée : toute réponse du modèle hors de cet ensemble est rejetée.
INTENTIONS = {
    "CHAT",
    "CODE_EXECUTION",
    "FRESH_INFO",
    "STUDIO",
    "BROWSER",
    "SWE_FIX",
    "REPO_ENGINEERING",
    "RAG_DOCS",
    "GRAPHRAG",
    "DEEP_REASONING",
    "DEEP_RESEARCH",
    "TREND_SEARCH",
    "VIDEO_ANALYSIS",
}

# --- Contrôle daté, évalué AVANT le modèle -------------------------------------
# Le tri d'intention est fait par un modèle. Or un modèle dont les connaissances
# s'arrêtent avant l'année en cours ne peut pas reconnaître qu'une question porte
# sur son propre futur : « qui a gagné la coupe du monde 2026 » lui paraît être
# une conversation ordinaire, et il répond de mémoire. Mesuré le 2026-08-26 sur
# la machine du propriétaire — la réponse a été « je n'ai pas les informations
# récentes », alors que le pipeline d'information fraîche existait pour cela.
#
# La date du système, elle, ne se trompe pas. Ce contrôle est donc déterministe
# et passe avant toute question posée au modèle.

ANNEE = re.compile(r"\b(19|20)\d{2}\b")

# Formulations qui portent sur un état ou un résultat courant. Elles ne
# déclenchent la vérification que si aucune année passée n'est citée : « qui a
# gagné la coupe du monde 1998 » est un fait acquis, pas une actualité.
FORMULATIONS_COURANTES = (
    # Résultats et compétitions
    "qui a gagné", "qui a gagne", "qui a remporté", "qui a remporte",
    "vainqueur", "gagnant", "résultat", "resultat", "score",
    "coupe du monde", "meilleur joueur", "championnat",
    # États et responsables du moment
    "qui est le", "qui est la", "qui sont les",
    "en ce moment", "actuellement", "aujourd'hui", "cette semaine",
    # Chiffres qui bougent
    "population", "combien coûte", "combien coute", "prix de", "cours de",
    # Versions et actualité
    "dernière version", "derniere version", "dernier modèle", "dernier modele",
    "actualité", "actualite", "dernières nouvelles", "dernieres nouvelles",
    # Demande explicite de l'utilisateur : elle prime toujours
    "cherche sur le web", "cherche sur internet",
)


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
STUDIO          : traiter une vidéo de bout en bout — vertical 9:16 et
                  sous-titres incrustés, en une seule demande.
BROWSER         : ouvrir un site, naviguer, remplir un formulaire.
SWE_FIX         : corriger un bug dans un fichier existant.
REPO_ENGINEERING: travailler sur plusieurs fichiers d'un dépôt à la fois.
RAG_DOCS        : répondre à partir des documents de l'utilisateur.
GRAPHRAG        : question sur les liens entre les documents.

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

    @staticmethod
    def exige_verification(user_input: str, aujourd_hui: Optional[datetime.date] = None) -> bool:
        """Dit si la question porte sur quelque chose que le modèle ne peut pas savoir.

        Deux cas, et un seul suffit :

        1. Une année **égale ou postérieure à l'année en cours** est citée. Aucun
           modèle déployé ne connaît l'issue de son propre futur.
        2. La question porte sur un état ou un résultat courant (« qui a gagné »,
           « dernière version », « prix de ») **et** ne cite aucune année passée.

        La date vient de l'horloge, jamais du modèle. `aujourd_hui` n'existe que
        pour que les tests fixent une date au lieu de dépendre du jour où ils
        tournent.
        """
        aujourd_hui = aujourd_hui or datetime.date.today()
        texte = user_input.lower()

        annees = [int(m.group()) for m in ANNEE.finditer(texte)]
        if any(annee >= aujourd_hui.year for annee in annees):
            return True

        if annees:  # une année est citée, et elle est passée : le fait est acquis
            return False

        return any(formulation in texte for formulation in FORMULATIONS_COURANTES)

    async def analyze_intent(self, user_input: str) -> str:
        """Détermine vers quel agent envoyer la demande.

        Le contrôle daté passe en premier : il ne coûte rien et il rattrape ce
        que le modèle ne peut pas voir. Ensuite seulement le modèle tranche.
        S'il est indisponible ou répond autre chose qu'une étiquette connue, on
        retombe sur les mots-clés — un repli moins fin, mais annoncé dans les
        journaux plutôt que silencieux.
        """
        if self.exige_verification(user_input):
            logger.info("Contrôle daté : la question demande une vérification -> FRESH_INFO")
            return "FRESH_INFO"

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

        # Capacites autrefois joignables uniquement en choisissant leur nom
        # dans le menu. Le menu n en propose plus que deux : elles doivent donc
        # etre atteignables depuis une phrase ordinaire.
        if any(k in text for k in ["navigue", "ouvre le site", "va sur http", "navigateur"]):
            return "BROWSER"
        if any(k in text for k in ["corrige le bug", "erreur dans le code", "corrige le fichier"]):
            return "SWE_FIX"
        if any(k in text for k in ["architecture du projet", "dépôt", "depot", "plusieurs fichiers"]):
            return "REPO_ENGINEERING"
        if any(k in text for k in ["dans mes documents", "d'après mon fichier", "mes devis", "mes factures"]):
            return "RAG_DOCS"
        if any(k in text for k in ["graphe de connaissance", "liens entre mes documents", "graphrag"]):
            return "GRAPHRAG"

        # Studio complet : une seule demande, toute la chaine.
        # Teste avant VIDEO_ANALYSIS : « sous-titre cette video » est un studio,
        # pas une analyse — l attente de l utilisateur est un fichier rendu.
        studio_keywords = [
            "studio", "transforme la vidéo", "transforme la video",
            "sous-titre", "sous titre", "9:16", "short tiktok", "reformatte",
        ]
        if any(k in text for k in studio_keywords):
            return "STUDIO"

        # Vidéo
        video_keywords = ["découpe cette vidéo", "analyse cette vidéo"]
        if any(k in text for k in video_keywords):
            return "VIDEO_ANALYSIS"

        return "CHAT"

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session_id = context.get("session_id", "default") if context else "default"
        owner_name = self.memory.get_fact("owner") if self.memory else "Usman"

        # La classification coûte un appel au modèle : si l'appelant l'a déjà
        # faite, on la réutilise au lieu de la refaire.
        intent = (context or {}).get("intent") or await self.analyze_intent(user_input)

        history = self.memory.get_recent_history(session_id=session_id, limit=6) if self.memory else []

        # PROMPT MONDIAL SANS BIAIS LOCAL FORCÉ
        system_prompt = (
            f"Tu es Usman, une intelligence artificielle internationale de haut niveau, au service de {owner_name}.\n"
            f"Contexte temporel : Nous sommes en 2026.\n"
            f"Règles strictes :\n"
            f"1. Réponds STRICTEMENT et DIRECTEMENT à la question posée sans dériver vers d'autres sujets.\n"
            f"2. Ne parle du Sénégal QUE si la question concerne explicitement le Sénégal.\n"
            f"3. Pour les événements futurs (ex: Coupe du Monde 2026), rappelle poliment que l'événement n'a pas encore eu lieu et donne les faits historiques connus si pertinents.\n"
            f"4. Réponds en français fluide, naturel et professionnel."
        )

        prompt_lines = []
        for msg in history:
            role_label = owner_name if msg["role"] == "user" else "Usman"
            prompt_lines.append(f"{role_label}: {msg['content']}")
        prompt_lines.append(f"{owner_name}: {user_input}")
        prompt_lines.append("Usman:")

        reply = await self.provider.generate(prompt="\n".join(prompt_lines), system_prompt=system_prompt)
        return {
            "intent": intent,
            "agent": self.name,
            "response": reply.strip()
        }
