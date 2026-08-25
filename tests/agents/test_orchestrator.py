"""Verifie que l Orchestrateur aiguille chaque phrase vers le bon agent.

Ce test est instantane : l aiguillage se fait par mots-cles, sans appel a l IA.
    Lancer avec :  .venv/Scripts/python.exe tests/agents/test_orchestrator.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from agents.orchestrator.orchestrator_agent import OrchestratorAgent

# (phrase de l utilisateur, agent attendu)
CAS = [
    ("Bonjour, comment vas-tu ?",                     "CHAT"),
    ("Ecris un script python pour trier une liste",   "CODE_EXECUTION"),
    ("Resous l equation x au carre moins 5x + 6",     "DEEP_REASONING"),
    ("Donne-moi une idée de vidéo pour TikTok",       "TREND_SEARCH"),
    ("Fais une recherche approfondie sur l IA",       "DEEP_RESEARCH"),
    ("Découpe cette vidéo en short vertical",         "VIDEO_ANALYSIS"),
    # Verifie qu un mot courant ne declenche plus un agent specialise :
    ("Parle-moi un peu de mon projet",                "CHAT"),
]


async def main():
    print("Test de l aiguillage de l Orchestrateur")
    print("-" * 62)

    agent = OrchestratorAgent(provider=OllamaProvider(), memory=None)
    echecs = []

    for phrase, attendu in CAS:
        obtenu = await agent.analyze_intent(phrase)
        marque = "OK  " if obtenu == attendu else "ECHEC"
        print("  %s  %-45s -> %s" % (marque, phrase[:45], obtenu))
        if obtenu != attendu:
            echecs.append((phrase, attendu, obtenu))

    print("-" * 62)
    if echecs:
        print("%d ECHEC(S) :" % len(echecs))
        for phrase, attendu, obtenu in echecs:
            print("   '%s'  attendu=%s  obtenu=%s" % (phrase, attendu, obtenu))
        sys.exit(1)

    print("Les %d aiguillages sont corrects." % len(CAS))


if __name__ == "__main__":
    asyncio.run(main())
