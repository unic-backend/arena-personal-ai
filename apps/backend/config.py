"""Réglages d'Usman, lus une seule fois au démarrage.

Tout ce qui vient de l'environnement vit ici, et rien d'autre. Un module de
configuration qui instancie des objets devient une dépendance de tout le reste :
celui-ci ne fait que lire.
"""
import logging
import os

from dotenv import load_dotenv

# BASE_DIR et la preparation de sys.path viennent du paquet : ils doivent etre
# en place avant l'import de n'importe quel module d'Usman.
from apps.backend import BASE_DIR

load_dotenv(dotenv_path=BASE_DIR / ".env")


def reglage(nom: str, defaut: str = "") -> str:
    """Lit `USMAN_<nom>`, et retombe sur `ARENA_<nom>` si elle seule existe.

    Le projet a ete renomme le 2026-08-26. Un `.env` deja rempli porte encore
    les anciens noms : les refuser d un coup arreterait le serveur du
    proprietaire sans qu il ait rien fait de mal. Le repli est **annonce**,
    jamais silencieux — un repli qu on ne voit pas devient permanent.
    """
    valeur = os.getenv(f"USMAN_{nom}")
    if valeur is not None:
        return valeur

    ancienne = os.getenv(f"ARENA_{nom}")
    if ancienne is not None:
        logging.getLogger("usman.config").warning(
            f"ARENA_{nom} est lue faute de USMAN_{nom}. Renomme-la dans .env."
        )
        return ancienne

    return defaut


# --- Emplacements -------------------------------------------------------------
MEDIA_DIR = BASE_DIR / "media"
RENDERED_DIR = MEDIA_DIR / "rendered"
DB_PATH = BASE_DIR / "data" / "database" / "memory.db"

# --- Origines autorisees (CORS) -----------------------------------------------
# Jamais « * » : le navigateur laisserait n'importe quel site appeler /api.
ORIGINES_PAR_DEFAUT = "http://localhost:3000,http://localhost:3080,http://localhost:8000"
ALLOWED_ORIGINS = [
    origine.strip()
    for origine in reglage("ALLOWED_ORIGINS", ORIGINES_PAR_DEFAUT).split(",")
    if origine.strip()
]

# --- Authentification ---------------------------------------------------------
# Absente, la passerelle refuse tout : le defaut est sur.
USMAN_API_KEY = reglage("API_KEY")

# --- Limitation de debit ------------------------------------------------------
# Un appel au modele occupe la carte graphique plusieurs secondes.
REQUETES_MAX = int(reglage("RATE_LIMIT_REQUESTS", "10"))
FENETRE_SECONDES = float(reglage("RATE_LIMIT_WINDOW", "60"))

# --- Envoi de fichiers --------------------------------------------------------
# Regle metier : Usman ne traite que de l'audio et de la video.
EXTENSIONS_MEDIA_AUTORISEES = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
}
# Reglage : depend du disque de la machine.
TAILLE_MAX_ENVOI = int(reglage("UPLOAD_MAX_BYTES", str(2 * 1024 * 1024 * 1024)))
# Le fichier est ecrit par blocs : tout lire d'un coup chargerait la memoire.
TAILLE_BLOC_ENVOI = 1024 * 1024

# --- Modeles locaux -----------------------------------------------------------
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MODELE_RAPIDE = os.getenv("CODER_LOCAL_MODEL", "qwen2.5-coder:14b")
MODELE_PROFOND = os.getenv("DEFAULT_LOCAL_MODEL", "qwen3.5:9b")

# --- Modeles distants (hybride) -----------------------------------------------
# Le cloud est arrive le 2026-08-28 (DEC-0009), pour la vitesse et pour rien
# d'autre. Ollama reste le defaut, le repli, et le seul chemin autorise pour ce
# qui est sensible. Aucune cle n'est ecrite ici : elles vivent dans .env.
#
# Ordre de precedence, et il est volontairement strict — le plus ferme gagne :
#   AI_LOCAL_ONLY=true      -> LOCAL_ONLY, quoi que disent les autres
#   AI_CLOUD_ENABLED=false  -> LOCAL_ONLY
#   sinon                   -> AI_MODE
MODE_LOCAL_SEUL = "LOCAL_ONLY"
MODE_HYBRIDE = "HYBRIDE"
MODE_CLOUD_PREFERE = "CLOUD_PREFERRED"
MODES_IA = (MODE_LOCAL_SEUL, MODE_HYBRIDE, MODE_CLOUD_PREFERE)


def _booleen(nom: str, defaut: str) -> bool:
    """Lit un drapeau. Tout ce qui n'est pas explicitement vrai est faux."""
    return os.getenv(nom, defaut).strip().lower() in ("1", "true", "vrai", "oui", "yes")


def _mode_ia() -> str:
    """Le regime d'inference, une fois les interrupteurs appliques.

    Un mode inconnu retombe sur HYBRIDE **en le disant** : un repli silencieux
    sur un reglage de confidentialite deviendrait permanent sans qu'il le sache.
    """
    if _booleen("AI_LOCAL_ONLY", "false") or not _booleen("AI_CLOUD_ENABLED", "true"):
        return MODE_LOCAL_SEUL
    demande = os.getenv("AI_MODE", MODE_HYBRIDE).strip().upper()
    if demande not in MODES_IA:
        logging.getLogger("usman.config").warning(
            "AI_MODE=%r inconnu : HYBRIDE est applique. Valeurs acceptees : %s.",
            demande, ", ".join(MODES_IA))
        return MODE_HYBRIDE
    return demande


MODE_IA = _mode_ia()

# Le fournisseur demande par le proprietaire. AUTO laisse l'aiguilleur decider.
FOURNISSEURS = ("AUTO", "LOCAL", "GROQ", "DEEPINFRA")
FOURNISSEUR_DEMANDE = os.getenv("AI_DEFAULT_PROVIDER", "AUTO").strip().upper()
if FOURNISSEUR_DEMANDE not in FOURNISSEURS:
    logging.getLogger("usman.config").warning(
        "AI_DEFAULT_PROVIDER=%r inconnu : AUTO est applique.", FOURNISSEUR_DEMANDE)
    FOURNISSEUR_DEMANDE = "AUTO"

# `OLLAMA_MODEL` est accepte comme nom principal ; les noms deja en place
# continuent de fonctionner. Un .env rempli ne doit pas cesser de marcher.
MODELE_LOCAL = os.getenv("OLLAMA_MODEL") or MODELE_PROFOND

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODELE = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

DEEPINFRA_API_KEY = os.getenv("DEEPINFRA_API_KEY", "")
DEEPINFRA_MODELE = os.getenv("DEEPINFRA_MODEL", "meta-llama/Llama-3.3-70B-Instruct")
DEEPINFRA_URL = os.getenv("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai")

# Garde-fous de depense. Atteints, ARENA retombe sur Ollama — il ne s'arrete pas.
# `0` veut dire « pas de plafond », et c'est un choix qui doit etre ecrit.
CLOUD_REQUETES_PAR_JOUR = int(os.getenv("AI_MAX_CLOUD_REQUESTS_PER_DAY", "200"))
CLOUD_COUT_MAX_PAR_REQUETE = float(os.getenv("AI_MAX_COST_PER_REQUEST", "0.02"))
CLOUD_BUDGET_JOURNALIER = float(os.getenv("AI_DAILY_BUDGET", "1.0"))

# Delai de connexion vers un service distant. Court **exprès** : sans reseau,
# ARENA doit basculer sur Ollama sans faire attendre une reponse de chat.
CLOUD_DELAI_CONNEXION = float(os.getenv("AI_CLOUD_CONNECT_TIMEOUT", "3.0"))
CLOUD_DELAI_TOTAL = float(os.getenv("AI_CLOUD_TIMEOUT", "60.0"))

# --- Aiguillage ---------------------------------------------------------------
# Intentions confiees a un agent specialise plutot qu a une reponse conversationnelle.
AGENTS_SPECIALISES = frozenset({
    "DEEP_REASONING", "DEEP_RESEARCH", "FRESH_INFO",
    "TREND_SEARCH", "CODE_EXECUTION", "VIDEO_ANALYSIS", "STUDIO",
    "BROWSER", "SWE_FIX", "REPO_ENGINEERING", "RAG_DOCS", "GRAPHRAG",
    "PLAQUISTE", "EMAIL",
})
