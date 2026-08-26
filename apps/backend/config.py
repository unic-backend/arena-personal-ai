"""Réglages d'ARENA, lus une seule fois au démarrage.

Tout ce qui vient de l'environnement vit ici, et rien d'autre. Un module de
configuration qui instancie des objets devient une dépendance de tout le reste :
celui-ci ne fait que lire.
"""
import os

from dotenv import load_dotenv

# BASE_DIR et la preparation de sys.path viennent du paquet : ils doivent etre
# en place avant l'import de n'importe quel module d'ARENA.
from apps.backend import BASE_DIR

load_dotenv(dotenv_path=BASE_DIR / ".env")

# --- Emplacements -------------------------------------------------------------
MEDIA_DIR = BASE_DIR / "media"
RENDERED_DIR = MEDIA_DIR / "rendered"
DB_PATH = BASE_DIR / "data" / "database" / "memory.db"

# --- Origines autorisees (CORS) -----------------------------------------------
# Jamais « * » : le navigateur laisserait n'importe quel site appeler /api.
ORIGINES_PAR_DEFAUT = "http://localhost:3000,http://localhost:3080,http://localhost:8000"
ALLOWED_ORIGINS = [
    origine.strip()
    for origine in os.getenv("ARENA_ALLOWED_ORIGINS", ORIGINES_PAR_DEFAUT).split(",")
    if origine.strip()
]

# --- Authentification ---------------------------------------------------------
# Absente, la passerelle refuse tout : le defaut est sur.
ARENA_API_KEY = os.getenv("ARENA_API_KEY", "")

# --- Limitation de debit ------------------------------------------------------
# Un appel au modele occupe la carte graphique plusieurs secondes.
REQUETES_MAX = int(os.getenv("ARENA_RATE_LIMIT_REQUESTS", "10"))
FENETRE_SECONDES = float(os.getenv("ARENA_RATE_LIMIT_WINDOW", "60"))

# --- Envoi de fichiers --------------------------------------------------------
# Regle metier : ARENA ne traite que de l'audio et de la video.
EXTENSIONS_MEDIA_AUTORISEES = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
}
# Reglage : depend du disque de la machine.
TAILLE_MAX_ENVOI = int(os.getenv("ARENA_UPLOAD_MAX_BYTES", str(2 * 1024 * 1024 * 1024)))
# Le fichier est ecrit par blocs : tout lire d'un coup chargerait la memoire.
TAILLE_BLOC_ENVOI = 1024 * 1024

# --- Modeles locaux -----------------------------------------------------------
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MODELE_RAPIDE = os.getenv("CODER_LOCAL_MODEL", "qwen2.5-coder:14b")
MODELE_PROFOND = os.getenv("DEFAULT_LOCAL_MODEL", "qwen3.5:9b")

# --- Aiguillage ---------------------------------------------------------------
# Intentions confiees a un agent specialise plutot qu a une reponse conversationnelle.
AGENTS_SPECIALISES = frozenset({
    "DEEP_REASONING", "DEEP_RESEARCH", "FRESH_INFO",
    "TREND_SEARCH", "CODE_EXECUTION", "VIDEO_ANALYSIS", "STUDIO",
    "BROWSER", "SWE_FIX", "REPO_ENGINEERING", "RAG_DOCS", "GRAPHRAG",
})
