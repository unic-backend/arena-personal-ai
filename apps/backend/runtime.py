"""Objets partagés d'Usman : mémoire, permissions, modèles et agents.

Ils sont créés une seule fois, au démarrage, et réutilisés par toutes les routes.
Les regrouper ici évite que chaque routeur en fabrique sa propre copie — deux
`MemoryManager` sur la même base, ou deux `OllamaProvider` qui rechargent chacun
le modèle en VRAM.
"""
import logging

from agents.browser.browser_agent import BrowserAgent
from agents.clip_selector.clip_selector_agent import ClipSelectorAgent
from agents.coder.coder_agent import CoderAgent
from agents.editor.editor_agent import EditorAgent
from agents.fresh_info.fresh_info_agent import FreshInfoAgent
from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from agents.plaquiste.plaquiste_agent import PlaquisteAgent
from agents.publisher.publisher_agent import PublisherAgent
from agents.repo_engineer.repo_engineer_agent import RepoEngineerAgent
from agents.researcher.researcher_agent import DeepResearcherAgent
from agents.subtitle.subtitle_agent import SubtitleAgent
from agents.swe_agent.swe_agent import SWEAgent
from agents.trend_analyzer.trend_analyzer_agent import TrendAnalyzerAgent
from agents.video_analyzer.video_analyzer_agent import VideoAnalyzerAgent
from apps.backend.config import DB_PATH, MODELE_PROFOND, MODELE_RAPIDE, OLLAMA_URL
from apps.backend.pieces_jointes import DepotPiecesJointes
from core.actions.attente import FileDAttente
from core.actions.journal import JournalDesActions
from core.connectors.galsen import GalsenConnector
from core.connectors.registre import RegistreConnecteurs
from core.memory.memory_manager import MemoryManager
from core.memory.personnelle import MemoirePersonnelle
from core.models.ollama_provider import OllamaProvider
from core.permissions.controle import ControleAcces
from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import PolitiqueDePermissions
from social.tiktok.tiktok_connector import TikTokConnector
from tools.rag.graphrag_tool import GraphRAGTool
from tools.rag.lightrag_tool import LightRAGTool

logger = logging.getLogger("usman.backend")

# --- Etat et outils -----------------------------------------------------------
memory = MemoryManager(db_path=str(DB_PATH))
permissions = PermissionManager()
# Politique fine (compte x service x action x risque) et controle qui la combine
# aux neuf coupe-circuits ci-dessus. La plus stricte des deux couches gagne.
politique = PolitiqueDePermissions()
acces = ControleAcces(permissions=permissions, politique=politique)

# --- Connecteurs --------------------------------------------------------------
# On declare des fabriques, pas des objets : rien n'est construit tant que
# personne ne s'en sert, et un connecteur qui echoue a naitre est mis hors
# service tout seul, sans empecher le serveur de demarrer.
registre = RegistreConnecteurs()
# La file d'attente execute par le registre, et le registre construit des
# connecteurs qui deposent dans la file. Le lien se fait par une fonction plutot
# que par un import croise : `attente.py` n'a jamais entendu parler du registre.
file_attente = FileDAttente(db_path=str(DB_PATH), executeur=registre.executer_confirmee)
registre.declarer(
    "tiktok",
    lambda: TikTokConnector(acces=acces, journal=journal, file_attente=file_attente),
)
# Premier connecteur reellement operationnel : GalsenAPI est publique, donc il
# ne depend d'aucun secret et n'est pas gele par la purge en attente.
registre.declarer(
    "galsen",
    lambda: GalsenConnector(acces=acces, journal=journal, file_attente=file_attente),
)
# Journal des actions a effet externe. Meme fichier que la memoire, table a part.
journal = JournalDesActions(db_path=str(DB_PATH))
# Memoire personnelle (souvenirs, entites, relations). Construite en phase 6.1
# et jusqu'ici lue par personne : c'est le defaut d'`agent_logs` qui recommencait.
memoire_personnelle = MemoirePersonnelle(db_path=str(DB_PATH))
# Pieces jointes : le fichier est lu puis efface, seul son texte reste en
# memoire le temps d'une conversation.
pieces_jointes = DepotPiecesJointes()
lightrag_tool = LightRAGTool()
graphrag_tool = GraphRAGTool()

# --- Modeles ------------------------------------------------------------------
fast_provider = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_RAPIDE)
deep_provider = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_PROFOND)

# --- Equipe complete d'agents -------------------------------------------------
orchestrator = OrchestratorAgent(provider=fast_provider, memory=memory)
trend_agent = TrendAnalyzerAgent(provider=deep_provider, memory=memory)
video_agent = VideoAnalyzerAgent(provider=deep_provider, memory=memory)
editor_agent = EditorAgent(provider=deep_provider, memory=memory)
subtitle_agent = SubtitleAgent(provider=deep_provider, memory=memory)
coder_agent = CoderAgent(provider=fast_provider, memory=memory)
researcher_agent = DeepResearcherAgent(provider=deep_provider, memory=memory)
clip_selector = ClipSelectorAgent(provider=deep_provider, memory=memory)
publisher_agent = PublisherAgent(
    provider=fast_provider, memory=memory, journal=journal, registre=registre
)
browser_agent = BrowserAgent(provider=fast_provider, memory=memory)
# Agent d'information fraiche : il lit le web avant de repondre.
fresh_agent = FreshInfoAgent(provider=fast_provider, memory=memory)
repo_engineer = RepoEngineerAgent(provider=fast_provider, memory=memory)
swe_agent = SWEAgent(provider=fast_provider, memory=memory)
# Metier UniC Plaquiste : redaction soignee, donc le modele profond.
plaquiste_agent = PlaquisteAgent(provider=deep_provider, memory=memory)

memory.set_fact("user_profile", "owner", "Ousmane", {"role": "Propriétaire et créateur d'Usman"})
