"""Objets partagés d'Usman : mémoire, permissions, modèles et agents.

Ils sont créés une seule fois, au démarrage, et réutilisés par toutes les routes.
Les regrouper ici évite que chaque routeur en fabrique sa propre copie — deux
`MemoryManager` sur la même base, ou deux `OllamaProvider` qui rechargent chacun
le modèle en VRAM.
"""
import logging
import os

from agents.audio.audio_agent import AudioAgent
from agents.browser.browser_agent import BrowserAgent
from agents.clip_selector.clip_selector_agent import ClipSelectorAgent
from agents.coder.coder_agent import CoderAgent
from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from agents.editor.editor_agent import EditorAgent
from agents.email.email_agent import EmailAgent
from agents.formel.formel_agent import FormelAgent
from agents.fresh_info.fresh_info_agent import FreshInfoAgent
from agents.montage.montage_agent import MontageAgent
from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from agents.plaquiste.plaquiste_agent import PlaquisteAgent
from agents.publisher.publisher_agent import PublisherAgent
from agents.repo_engineer.repo_engineer_agent import RepoEngineerAgent
from agents.researcher.researcher_agent import DeepResearcherAgent
from agents.social.social_agent import SocialAgent
from agents.subtitle.subtitle_agent import SubtitleAgent
from agents.swe_agent.swe_agent import SWEAgent
from agents.trend_analyzer.trend_analyzer_agent import TrendAnalyzerAgent
from agents.ui.ui_agent import UiGenerationAgent
from agents.video.production_agent import VideoProductionAgent
from agents.video_analyzer.video_analyzer_agent import VideoAnalyzerAgent
from agents.vision.vision_agent import VisionAgent
from apps.backend.config import (
    CLOUD_BUDGET_JOURNALIER,
    CLOUD_REQUETES_PAR_JOUR,
    DB_PATH,
    FOURNISSEUR_DEMANDE,
    MODE_IA,
    MODELE_CODEUR,
    MODELE_PROFOND,
    MODELE_RAPIDE,
    MODELE_VISION,
    OLLAMA_URL,
)
from apps.backend.pieces_jointes import DepotPiecesJointes
from core.actions.attente import FileDAttente
from core.actions.journal import JournalDesActions
from core.agent.capacites import RegistreCapacites, adaptateur_synchrone
from core.connectors.audio_voix import ConnecteurAudioVoix
from core.connectors.browser import ConnecteurBrowser
from core.connectors.calendrier import CalendrierConnector
from core.connectors.claude_context import ConnecteurClaudeContext
from core.connectors.devis import DevisConnector
from core.connectors.drift import ConnecteurDrift
from core.connectors.faceplugin import ConnecteurFaceplugin
from core.connectors.formbricks import ConnecteurFormbricks
from core.connectors.galsen import GalsenConnector
from core.connectors.gitingest import ConnecteurGitIngest
from core.connectors.gmail import GmailConnector
from core.connectors.graphify import ConnecteurGraphify
from core.connectors.hermes_evolution import ConnecteurHermesEvolution
from core.connectors.ifc import ConnecteurIfc
from core.connectors.ifc_generation import ConnecteurIfcGeneration
from core.connectors.krillinai import ConnecteurKrillinAI
from core.connectors.lean_formel import ConnecteurLeanFormel
from core.connectors.moneyprinter import MoneyPrinterConnector
from core.connectors.montage import ConnecteurMontage
from core.connectors.opentakeoff import ConnecteurOpenTakeoff
from core.connectors.openviking import ConnecteurOpenViking
from core.connectors.registre import RegistreConnecteurs
from core.connectors.securite_chantier import ConnecteurSecuriteChantier
from core.connectors.stockage_jetons import charger_tout as _charger_jetons_persistants
from core.connectors.txtai_search import ConnecteurTxtaiSearch
from core.connectors.ui_generate import ConnecteurUiGenerate
from core.connectors.ui_ux_pro_max import ConnecteurUiUxProMax
from core.connectors.wan2gp import Wan2GPConnector
from core.connectors.workflow_guide import ConnecteurWorkflowGuide
from core.connectors.xaar_kaname import XaarKanameConnector
from core.conversations.depot import DepotConversations
from core.execution.disjoncteur import Disjoncteur
from core.execution.hooks import RegistreDeCrochets
from core.execution.mesures import Rapport
from core.execution.travaux import FileDeTravaux
from core.guardian.file_maintenance import FileDeMaintenance
from core.guardian.gardien import Gardien
from core.memory.memory_manager import MemoryManager
from core.memory.personnelle import MemoirePersonnelle
from core.memory.semantique import IndexSemantique
from core.models.deepinfra_provider import DeepInfraProvider
from core.models.groq_provider import GroqProvider
from core.models.ollama_provider import OllamaProvider
from core.models.routeur import RouteurModeles
from core.models.usage import CompteurUsage
from core.permissions.controle import ControleAcces
from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import PolitiqueDePermissions
from core.reasoning.reasoning_engine import ReasoningEngine
from social.tiktok.tiktok_connector import TikTokConnector
from tools.atelier import Atelier
from tools.rag.graphrag_tool import GraphRAGTool
from tools.rag.lightrag_tool import LightRAGTool
from tools.rag.lightrag_tool import est_un_echec as lightrag_echec

logger = logging.getLogger("usman.backend")

# --- Etat et outils -----------------------------------------------------------
memory = MemoryManager(db_path=str(DB_PATH))
# Le coffre a conversations : ce que ses appareils se partagent (VOLET synchro).
depot_conversations = DepotConversations(db_path=str(DB_PATH))
permissions = PermissionManager()
# Politique fine (compte x service x action x risque) et controle qui la combine
# aux neuf coupe-circuits ci-dessus. La plus stricte des deux couches gagne.
politique = PolitiqueDePermissions()
acces = ControleAcces(permissions=permissions, politique=politique)

# --- Connecteurs --------------------------------------------------------------
# Jetons OAuth obtenus par /connectors/{id}/auth (chapitre 8.2, DEC-0024) :
# une variable deja presente dans l'environnement (Railway, .env local) gagne
# toujours ; ce qui est recharge ici ne fait que retrouver un jeton obtenu
# lors d'un demarrage precedent, sur un hebergement sans fichier .env pour le
# porter (trouve le 31/08/2026 : un redeploiement perdait un jeton qui
# n'avait jamais vecu qu'en memoire du processus precedent).
for _variable, _valeur in _charger_jetons_persistants(str(DB_PATH)).items():
    os.environ.setdefault(_variable, _valeur)

# On declare des fabriques, pas des objets : rien n'est construit tant que
# personne ne s'en sert, et un connecteur qui echoue a naitre est mis hors
# service tout seul, sans empecher le serveur de demarrer.
registre = RegistreConnecteurs()
# La file d'attente execute par le registre, et le registre construit des
# connecteurs qui deposent dans la file. Le lien se fait par une fonction plutot
# que par un import croise : `attente.py` n'a jamais entendu parler du registre.
file_attente = FileDAttente(db_path=str(DB_PATH), executeur=registre.executer_confirmee)
# Crochets autour de l'execution (DEC-0013) : partages par tous les
# connecteurs, comme journal/file_attente. Premier consommateur reel — un
# disjoncteur qui coupe court apres des echecs consecutifs REELS, au lieu de
# repayer le meme delai d'attente a chaque appel d'un service tombe.
crochets = RegistreDeCrochets()
disjoncteur = Disjoncteur()
crochets.avant(disjoncteur.avant_execution)
crochets.apres(disjoncteur.apres_execution)
registre.declarer(
    "tiktok",
    lambda: TikTokConnector(acces=acces, journal=journal, file_attente=file_attente,
                            crochets=crochets),
)
# Premier connecteur reellement operationnel : GalsenAPI est publique, donc il
# ne depend d'aucun secret et n'est pas gele par la purge en attente.
# Video courte a partir d'un sujet : script, plans, voix, sous-titres, montage.
# Service separe (MoneyPrinterTurbo), lance par le proprietaire ; ARENA lui parle
# par son API. Non configure tant qu'il n'est pas lance — la sonde le mesure.
registre.declarer(
    "moneyprinter",
    lambda: MoneyPrinterConnector(acces=acces, journal=journal, file_attente=file_attente,
                                  crochets=crochets),
)
# Generation d'images video. Non configure tant que WanGP n'est pas lance : la
# sonde le mesure au lieu de le supposer.
registre.declarer(
    "wan2gp",
    lambda: Wan2GPConnector(acces=acces, journal=journal, file_attente=file_attente,
                            crochets=crochets),
)
# Devis PDF : chiffrage libre, production du document derriere confirmation.
registre.declarer(
    "devis",
    lambda: DevisConnector(acces=acces, journal=journal, file_attente=file_attente,
                           crochets=crochets),
)
# Guide de procedure : un workflow deja decrit (jamais capture en direct)
# transforme en PDF/DOCX/HTML/Markdown. Voir core/connectors/workflow_guide.py,
# DEC-0048.
registre.declarer(
    "workflow_guide",
    lambda: ConnecteurWorkflowGuide(acces=acces, journal=journal, file_attente=file_attente,
                                    crochets=crochets),
)
registre.declarer(
    "xaar_kaname",
    lambda: XaarKanameConnector(acces=acces, journal=journal, file_attente=file_attente,
                                crochets=crochets),
)
# Analyse de visages : SDK Faceplugin, installe a cote (hors depot, aucune
# licence declaree). Detecter et reperer sont des lectures ; extraire un
# gabarit et comparer sont de la biometrie et passent par la confirmation.
registre.declarer(
    "faceplugin",
    lambda: ConnecteurFaceplugin(acces=acces, journal=journal,
                                 file_attente=file_attente, crochets=crochets),
)
# Intelligence de design : UI/UX Pro Max (MIT), moteur local en Python pur.
# Lecture seule — son option d'ecriture sur disque n'est pas exposee.
registre.declarer(
    "ui_ux_pro_max",
    lambda: ConnecteurUiUxProMax(acces=acces, journal=journal,
                                 file_attente=file_attente, crochets=crochets),
)
# Metre de plan PDF : moteur OpenTakeoff, installe a cote (DEC-0008), jamais
# dans ce depot. Non configure tant qu'il n'est pas construit sur sa machine —
# la sonde le mesure au lieu de le supposer.
registre.declarer(
    "opentakeoff",
    lambda: ConnecteurOpenTakeoff(acces=acces, journal=journal, file_attente=file_attente,
                                  crochets=crochets),
)
# Graphe structurel du depot : Graphify (Apache-2.0), tree-sitter, hors ligne.
# Cartographie CE depot (agents/, core/, apps/, tools/) — pas un second RAG,
# pas un generateur de PDF. Voir core/connectors/graphify.py, DEC-0046.
registre.declarer(
    "graphify",
    lambda: ConnecteurGraphify(acces=acces, journal=journal, file_attente=file_attente,
                               crochets=crochets),
)
# Un depot (local ou une URL) transforme en resume+arbre+contenu : GitIngest
# (MIT), API Python directe, aucun processus a surveiller. Complementaire a
# Graphify (structure) : celui-ci donne le contenu brut. Voir
# core/connectors/gitingest.py, DEC-0047.
registre.declarer(
    "gitingest",
    lambda: ConnecteurGitIngest(acces=acces, journal=journal, file_attente=file_attente,
                                crochets=crochets),
)
# BIM/IFC (mission BIM/metre/securite chantier, 05/09/2026) : lecture d'un
# fichier IFC via IfcOpenShell (LGPL-3.0-or-later), en bibliotheque Python
# jamais en code copie. Complementaire au metre de plan PDF (OpenTakeoff) :
# un plan PDF est mesure, un fichier IFC est LU — ses quantites (surface des
# murs) viennent du fichier lui-meme, jamais recalculees par geometrie dans
# cette phase. Voir core/connectors/ifc.py, DEC-0053.
registre.declarer(
    "ifc",
    lambda: ConnecteurIfc(acces=acces, journal=journal, file_attente=file_attente,
                          crochets=crochets),
)
# Generation IFC (mission BIM, 06/09/2026) : un croquis minimal de cloison
# (une face, longueur x hauteur), via l'API d'ecriture d'IfcOpenShell
# elle-meme — jamais un second moteur BIM (BIM as Code/BuildingPy refuses,
# DEC-0056). Ecrit dans media/rendered/, comme le devis. Voir
# core/connectors/ifc_generation.py.
registre.declarer(
    "ifc_generation",
    lambda: ConnecteurIfcGeneration(acces=acces, journal=journal, file_attente=file_attente,
                                    crochets=crochets),
)
# Securite chantier (mission BIM/metre/securite chantier, 05/09/2026) :
# detection EPI (casque, gilet...) sur une photo, appelee via SiteGuard
# (C-Nekopedia/SiteGuard, MIT) — un programme SEPARE installe a cote, jamais
# dans ce depot (SiteGuard depend lui-meme d'Ultralytics YOLO, AGPL-3.0).
# Consomme par VisionAgent, jamais un aiguillage automatique dedie. Voir
# core/connectors/securite_chantier.py.
registre.declarer(
    "securite_chantier",
    lambda: ConnecteurSecuriteChantier(acces=acces, journal=journal, file_attente=file_attente,
                                       crochets=crochets),
)
# Hermes Agent Self-Evolution (DEC-0055) : fait evoluer un depot CIBLE
# (hermes-agent, NousResearch/hermes-agent-self-evolution, MIT) — jamais
# ARENA lui-meme, garde structurelle dans le connecteur (DEC-0014 :
# aucune PR autonome sur ce depot, meme relue avant fusion). Sous-processus
# externe, jamais importe. Voir core/connectors/hermes_evolution.py.
registre.declarer(
    "hermes_evolution",
    lambda: ConnecteurHermesEvolution(acces=acces, journal=journal, file_attente=file_attente,
                                      crochets=crochets),
)
# Sondages/feedback (DEC-0052) : une instance Formbricks EXTERNE, appelee par
# son API REST publique — aucune ligne de son code (coeur AGPLv3) n'est
# copiee ici, meme frontiere que VoiceStudio. Aucune URL par defaut : sans
# FORMBRICKS_BASE_URL/API_KEY/WORKSPACE_ID explicitement configures, ce
# connecteur reste NON_CONFIGURE proprement — ARENA continue de fonctionner.
# Voir core/connectors/formbricks.py.
registre.declarer(
    "formbricks",
    lambda: ConnecteurFormbricks(acces=acces, journal=journal, file_attente=file_attente,
                                 crochets=crochets),
)
# Traduction/doublage d'une video EXISTANTE (sous-titres, TTS, rendu, cover) :
# l'ancien moteur KrillinAI, GPL-3.0, appele par sous-processus isole — jamais
# importe (meme frontiere que VoiceStudio/AGPL, core/connectors/audio_voix.py).
# Jamais de clonage vocal, jamais une seconde transcription locale : voir
# core/connectors/krillinai.py, DEC-0049.
registre.declarer(
    "krillinai",
    lambda: ConnecteurKrillinAI(acces=acces, journal=journal, file_attente=file_attente,
                                crochets=crochets),
)
# Drift (DEC-0057) : editeur video (GPLv3) pilote par son PROPRE serveur MCP,
# jamais importe ni copie — meme frontiere que KrillinAI/VoiceStudio. Reserve
# EXCLUSIVEMENT au workspace Video (agents/video/production_agent.py) : aucun
# chemin plaquiste/BIM/metier n'y touche. Aucune URL ni jeton par defaut
# (DEC-0002) : NON_CONFIGURE tant que DRIFT_MCP_URL/DRIFT_MCP_TOKEN ne sont
# pas dans le .env. Voir core/connectors/drift.py.
registre.declarer(
    "drift",
    lambda: ConnecteurDrift(acces=acces, journal=journal, file_attente=file_attente,
                            crochets=crochets),
)
# Claude Context (DEC-0058) : recherche semantique de code, par son propre
# serveur MCP (@zilliz/claude-context-mcp, MIT) — Milvus auto-heberge +
# Ollama local forces par le connecteur lui-meme, jamais Zilliz Cloud/OpenAI
# par defaut. Voir core/connectors/claude_context.py.
registre.declarer(
    "claude_context",
    lambda: ConnecteurClaudeContext(acces=acces, journal=journal, file_attente=file_attente,
                                    crochets=crochets),
)
# OpenViking (DEC-0058) : contexte hierarchique/memoire/competences, par son
# propre serveur HTTP (AGPLv3) — un service SEPARE, auto-heberge par le
# proprietaire, jamais importe. Explicite, jamais appele a la place de
# core/memory/ (meme discipline que txtai, DEC-0051). Voir
# core/connectors/openviking.py.
registre.declarer(
    "openviking",
    lambda: ConnecteurOpenViking(acces=acces, journal=journal, file_attente=file_attente,
                                 crochets=crochets),
)
# Navigation Web autonome (DEC-0059) : browser-use + Playwright/Chromium
# local, Lightpanda (AGPLv3, service externe, jamais importe) comme moteur
# optionnel plus leger derriere le meme contrat, avec repli automatique.
# Corrige au passage le seul chemin d'ARENA qui agissait sur le web sans
# passer par ce registre. Voir core/connectors/browser.py.
registre.declarer(
    "browser",
    lambda: ConnecteurBrowser(acces=acces, journal=journal, file_attente=file_attente,
                              crochets=crochets),
)
# Verification FORMELLE (DEC-0067) : Lean tranche, jamais le modele. ARENA
# savait calculer (bac a sable Python, sympy) ; elle ne savait pas prouver.
# La discipline vient du depot `anthropics/fermats-last-theorem` (Apache-2.0)
# et tient en une ligne : une preuve trouee COMPILE (code 0), donc le verdict
# se lit dans les axiomes, jamais dans le code de sortie.
# Voir core/connectors/lean_formel.py.
registre.declarer(
    "formel",
    lambda: ConnecteurLeanFormel(acces=acces, journal=journal,
                                 file_attente=file_attente, crochets=crochets),
)
# Generation d'interface : la technique d'OpenUI (prompt -> HTML/React/
# Svelte/Web-Component), jamais son serveur (connexion GitHub requise,
# weave/boto3/peewee/fastapi-sso qu'ARENA n'a pas besoin d'heberger). Ce
# connecteur ne genere rien lui-meme : agents/ui/ui_agent.py appelle le
# modele, ceci valide (aucun script externe hors liste fermee) et ecrit.
# Voir core/connectors/ui_generate.py, DEC-0050.
registre.declarer(
    "ui_generate",
    lambda: ConnecteurUiGenerate(acces=acces, journal=journal, file_attente=file_attente,
                                 crochets=crochets),
)
# Recherche semantique txtai (DEC-0051) : un moteur A COTE, jamais un
# remplacement — ARENA a deja une memoire retrouvee par le sens et deux
# moteurs de documents (LightRAG, GraphRAG). Aucune branche d'aiguillage
# automatique ne pointe ici : c'est une capacite explicite, pour un banc de
# comparaison, jamais appelee a la place d'un moteur existant. Le vecteur
# vient d'Ollama (embeddings_ollama, deja utilise par la memoire de chat) —
# aucun second modele. Voir core/connectors/txtai_search.py.
registre.declarer(
    "txtai_search",
    lambda: ConnecteurTxtaiSearch(acces=acces, journal=journal, file_attente=file_attente,
                                  crochets=crochets),
)
# Montage video : batir une timeline (lecture) et la rendre (ecriture, donc
# confirmation). Le moteur de rendu est ffmpeg, deja local et compatible avec
# sa RTX A2000 — voir docs/audits/opencut_audit.md pour pourquoi ce n'est pas
# celui d'OpenCut, dont le rendu est natif navigateur et le depot archive.
# Audio et voix : VoiceStudio, pilote par HTTP sur la boucle locale. C'est un
# programme SEPARE (AGPL-3.0) — aucune de ses lignes n'entre dans ARENA, dont
# la licence est proprietaire. Detail -> docs/audits/voicestudio_audit.md.
registre.declarer(
    "audio",
    lambda: ConnecteurAudioVoix(acces=acces, journal=journal,
                                file_attente=file_attente, crochets=crochets),
)
registre.declarer(
    "montage",
    lambda: ConnecteurMontage(acces=acces, journal=journal, file_attente=file_attente,
                              crochets=crochets),
)
registre.declarer(
    "galsen",
    lambda: GalsenConnector(acces=acces, journal=journal, file_attente=file_attente,
                            crochets=crochets),
)
# Courrier : LECTURE SEULE (chapitre 8.1). Aucune capacite d'ecriture n'est
# declaree, donc aucune n'existe — l'envoi viendra en 8.2, derriere
# confirmation. Non configure tant que les trois valeurs OAuth ne sont pas dans
# le .env : la sonde le mesure au lieu de le supposer.
# Agenda : lire, calculer ses creneaux libres, voir ce qui tombe dessus. Poser
# un rendez-vous est une ecriture, donc une confirmation. Meme identifiant
# Google que le courrier, autre portee.
registre.declarer(
    "calendrier",
    lambda: CalendrierConnector(acces=acces, journal=journal, file_attente=file_attente,
                                crochets=crochets),
)
registre.declarer(
    "gmail",
    lambda: GmailConnector(acces=acces, journal=journal, file_attente=file_attente,
                           crochets=crochets),
)
# Journal des actions a effet externe. Meme fichier que la memoire, table a part.
journal = JournalDesActions(db_path=str(DB_PATH))
# Memoire personnelle (souvenirs, entites, relations). Construite en phase 6.1
# et jusqu'ici lue par personne : c'est le defaut d'`agent_logs` qui recommencait.
memoire_personnelle = MemoirePersonnelle(db_path=str(DB_PATH))
# L'index des vecteurs vit ici, et non dans la passerelle : cree a chaque
# question, son cache serait vide a chaque question, et chaque tour de chat
# repaierait la vectorisation de toute la memoire. Il est partage et il dure.
index_semantique = IndexSemantique()
# Pieces jointes : le fichier est lu puis efface, seul son texte reste en
# memoire le temps d'une conversation.
pieces_jointes = DepotPiecesJointes()
lightrag_tool = LightRAGTool()
graphrag_tool = GraphRAGTool()

# --- Travaux de fond ----------------------------------------------------------
# Une seule carte graphique, donc une seule file : dix travaux soumis ne font pas
# dix travaux simultanes. Elle porte aujourd'hui le suivi des generations video,
# et c'est ce qui permet a « ou en est ma video ? » de repondre sans que le chat
# attende la carte.
travaux = FileDeTravaux()

# --- Mesures d'execution ------------------------------------------------------
# Les voies declarent des cibles ; ce rapport garde ce que les reponses ont
# reellement coute, pour que les deux soient confrontables. Il est lu par
# `/api/observability`. Une scene qui n'a pas tourne n'y entre pas avec un
# zero : elle n'y entre pas du tout, et le rapport le dit.
mesures_execution = Rapport()

# --- Gardien (DEC-0014) --------------------------------------------------------
# Un cycle de diagnostic reel (ruff, pytest, orphelins) qui alimente une
# memoire de maintenance persistante — jamais une modification autonome du
# depot. `GET /api/gardien/rapport` et `POST /api/gardien/cycle` le lisent
# et le declenchent ; voir core/guardian/gardien.py sur la limite volontaire.
file_maintenance = FileDeMaintenance(db_path=str(DB_PATH))
gardien = Gardien(file_maintenance=file_maintenance)

# --- Modeles ------------------------------------------------------------------
# Ollama reste le defaut, le repli, et le seul chemin pour ce qui est sensible
# (DEC-0009). Les deux fournisseurs distants n'existent que s'ils ont une cle :
# sans elle, l'aiguilleur ne les compte meme pas comme une option.
ollama_rapide = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_RAPIDE)
# Le modele de code, rendu aux deux agents dont c'est le metier. Avant le
# 02/09/2026 il n'existait pas separement : `fast_provider` portait
# `qwen2.5-coder` et repondait AUSSI a la conversation, aux devis et au
# courrier. Le proprietaire ne programme pas.
ollama_codeur = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_CODEUR)
ollama_profond = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_PROFOND)
# La vision reste locale, sans aiguilleur hybride (DEC-0019) : Groq et
# DeepInfra ne servent aucun modele de vision dans ce projet — les faire
# passer par l'aiguilleur ferait perdre l'image en silence des qu'Ollama
# manquerait, en repondant quand meme sur le texte seul.
ollama_vision = OllamaProvider(base_url=OLLAMA_URL, model_name=MODELE_VISION)

# Un seul compteur pour les deux aiguilleurs : le budget du jour est celui du
# proprietaire, pas celui d'un chemin de reponse.
compteur_usage = CompteurUsage(requetes_par_jour=CLOUD_REQUETES_PAR_JOUR,
                               budget_journalier=CLOUD_BUDGET_JOURNALIER)


def _aiguilleur(local: OllamaProvider) -> RouteurModeles:
    """Un aiguilleur pose devant un modele local. Le reste d'ARENA ne voit que lui."""
    return RouteurModeles(
        local=local,
        distants={"groq": GroqProvider(), "deepinfra": DeepInfraProvider()},
        mode=MODE_IA, fournisseur_demande=FOURNISSEUR_DEMANDE,
        compteur=compteur_usage,
    )


# Ces deux noms sont ceux que tout le projet importe depuis toujours. Ils
# designent maintenant un aiguilleur au lieu d'un fournisseur unique — et
# comme il implemente `ModelProvider`, rien d'autre n'a eu a changer.
fast_provider = _aiguilleur(ollama_rapide)
deep_provider = _aiguilleur(ollama_profond)
#: Reserve a ce qui ecrit du code. Le reste d'ARENA ne doit pas le voir.
coder_provider = _aiguilleur(ollama_codeur)

# --- Equipe complete d'agents -------------------------------------------------
orchestrator = OrchestratorAgent(provider=fast_provider, memory=memory)
trend_agent = TrendAnalyzerAgent(provider=deep_provider, memory=memory)
# L'agent video recoit de quoi suivre une generation : le registre pour joindre
# WanGP, la file pour le faire en fond, le journal pour retrouver l'identifiant
# de la derniere generation acceptee.
video_agent = VideoAnalyzerAgent(provider=deep_provider, memory=memory,
                                 registre=registre, travaux=travaux, journal=journal)
vision_agent = VisionAgent(provider=ollama_vision, memory=memory, pieces_jointes=pieces_jointes,
                          registre=registre)
# Montage : la phrase du proprietaire devient un plan d operations validees
# (`core/montage/planificateur.py`), jamais un pilotage direct de la timeline.
# Le modele profond, parce que produire un JSON structure et coherent est une
# redaction, pas une classification. Le registre lui donne le connecteur
# `montage` — donc la meme confirmation que le devis PDF avant tout rendu.
# Audio : sa phrase choisit la capacite (lire, transcrire, lister). Le modele
# rapide suffit — le classement se fait par mots-cles, et c'est la MACHINE qui
# parle et qui ecoute, pas le modele de langue.
audio_agent = AudioAgent(provider=fast_provider, memory=memory, registre=registre)
montage_agent = MontageAgent(provider=deep_provider, memory=memory, registre=registre)
editor_agent = EditorAgent(provider=deep_provider, memory=memory)
subtitle_agent = SubtitleAgent(provider=deep_provider, memory=memory)
coder_agent = CoderAgent(provider=coder_provider, memory=memory)
researcher_agent = DeepResearcherAgent(provider=deep_provider, memory=memory)
clip_selector = ClipSelectorAgent(provider=deep_provider, memory=memory)
publisher_agent = PublisherAgent(
    provider=fast_provider, memory=memory, journal=journal, registre=registre
)
browser_agent = BrowserAgent(provider=fast_provider, memory=memory, registre=registre)
# Preuve formelle (DEC-0067) : agent MINCE — il traduit la phrase en
# capacite du connecteur `formel`, il ne raisonne pas a la place du
# moteur existant. `deep_provider` : ecrire du Lean juste est une tache
# de raisonnement, pas de conversation.
formel_agent = FormelAgent(provider=deep_provider, memory=memory, registre=registre)
# Agent d'information fraiche : il lit le web avant de repondre.
fresh_agent = FreshInfoAgent(provider=fast_provider, memory=memory)
repo_engineer = RepoEngineerAgent(provider=fast_provider, memory=memory, registre=registre)
swe_agent = SWEAgent(provider=coder_provider, memory=memory)
# Dioumtoukay : celui qui AGIT sur la machine (DEC-0038). Il recoit le
# modele de code, et le journal — chacune de ses actions y laisse une trace,
# qui est ce que le proprietaire relit apres coup.
dioumtoukay_agent = DioumtoukayAgent(
    provider=coder_provider, memory=memory,
    atelier=Atelier(journal=journal),
    memoire_longue=memoire_personnelle)
# Raisonnement profond : plan, calcul reellement execute en bac a sable, puis
# synthese. Le modele profond, parce que c'est la voie PROFONDE qui l'emprunte.
# `/health` annoncait « ReasoningEngine » parmi les agents actifs alors qu'aucun
# chemin de reponse ne l'atteignait : l'annonce est desormais vraie.
reasoning_engine = ReasoningEngine(provider=deep_provider)
# Courrier : tri et brouillons. Le modele rapide suffit — trier cinq messages
# n'est pas une demonstration. L'envoi passe par le registre, donc par la
# confirmation, et l'agent ne connait aucun autre chemin.
email_agent = EmailAgent(provider=fast_provider, memory=memory, registre=registre)
# Reseaux sociaux : redaction soignee, donc le modele profond. Sa voix vit dans
# la memoire personnelle, et la recherche web sert la recherche de niche —
# absente, la capacite se declare indisponible au lieu d'inventer des tendances.
social_agent = SocialAgent(provider=deep_provider, memory=memory,
                           memoire_personnelle=memoire_personnelle,
                           registre=registre)
# Metier UniC Plaquiste : redaction soignee, donc le modele profond.
# `provider_vision` : le meme `ollama_vision` que VisionAgent (DEC-0019) —
# un second avis, visuel, sur les ouvertures d'un plan (DEC-0022), jamais
# un second modele construit pour cet agent seul.
plaquiste_agent = PlaquisteAgent(
    provider=deep_provider, memory=memory, registre=registre,
    pieces_jointes=pieces_jointes, memoire_personnelle=memoire_personnelle,
    provider_vision=ollama_vision)
# Orchestrateur Video (DEC-0037) : compose les capacites deja construites
# ci-dessus sur un meme projet, plutot que d'en reconstruire une equipe a
# part. Le modele profond pour proposer un graphe (une redaction structuree,
# comme le montage) ; `provider_vision` le meme `ollama_vision` que
# VisionAgent et PlaquisteAgent, jamais un second modele pour ce seul agent.
video_production_agent = VideoProductionAgent(
    provider=deep_provider, memory=memory, provider_vision=ollama_vision,
    video_analyzer_agent=video_agent, audio_agent=audio_agent,
    montage_agent=montage_agent, registre=registre)
# Generation d'interface (DEC-0050) : produire du code d'interface est une
# redaction structuree (comme le montage/le devis), donc le modele profond.
ui_agent = UiGenerationAgent(provider=deep_provider, memory=memory, registre=registre)

memory.set_fact("user_profile", "owner", "Ousmane", {"role": "Propriétaire et créateur d'Usman"})

# --- Capacites entre espaces (VOLET « espaces separes », phase 3) --------------
# Le canal par lequel un espace de la PWA peut en demander un autre — voir
# `core/agent/capacites.py`. Rempli ici, et nulle part ailleurs : ce module
# est le seul a avoir deja construit les cinq agents en meme temps, ce que
# `core/agent/capacites.py` refuse volontairement de faire lui-meme pour ne
# jamais dependre de ce fichier (import circulaire des qu'un agent voudrait
# a son tour appeler `capacites.demander`).
#
# Les identifiants sont ceux choisis dans la barre laterale de la PWA
# (`apps/pwa/src/lib/capacites/index.ts`) et ceux que l'orchestrateur route
# deja directement (`INTENTION_PAR_ESPACE`, VOLET phase 2) : les memes cinq,
# le meme sens.
capacites = RegistreCapacites()
capacites.enregistrer("code", coder_agent)
capacites.enregistrer("plaquiste", plaquiste_agent)
capacites.enregistrer("video", video_agent)
capacites.enregistrer("web", fresh_agent)
# LightRAGTool.query() est synchrone et rend une chaine, pas le dictionnaire
# structure que rendent les agents : adapte une fois ici, jamais a l'appel.
capacites.enregistrer("documents", adaptateur_synchrone(
    lambda texte: lightrag_tool.query(texte, mode="hybrid"), "LightRAG",
    est_un_echec=lightrag_echec,
))


#: Les moteurs qui repondent a une intention sans etre des `BaseAgent` :
#: `DEEP_REASONING`, `RAG_DOCS` et `GRAPHRAG` les atteignent depuis
#: `apps/backend/routers/chat.py`. Ecrits ici parce qu'ils n'ont aucune
#: classe commune a interroger — mais chacun est verifie par un test.
MOTEURS_NON_AGENTS = ("ReasoningEngine", "LightRAG", "MicrosoftGraphRAG")


def agents_actifs() -> list:
    """Les agents reellement construits par ce module, plus les trois moteurs.

    **Derivee, jamais ecrite a la main.** `/health` portait une liste figee
    qui avait derive : elle annoncait `ReasoningEngine` sans chemin pour
    l'atteindre (corrige en 2026-08), puis, l'inverse, elle taisait six
    agents bien vivants — `PlaquisteAgent`, `EmailAgent`, `SocialAgent`,
    `VisionAgent`, `MontageAgent`, `AudioAgent` (mesure du 01/09/2026).

    Une liste ecrite a la main derive toujours ; celle-ci ne peut pas.
    """
    from core.agent.base_agent import BaseAgent

    trouves = {objet.name for objet in globals().values()
               if isinstance(objet, BaseAgent)}
    return sorted(trouves) + list(MOTEURS_NON_AGENTS)
