import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider

async def main():
    print("Connexion a Ollama local...")
    provider = OllamaProvider(model_name="qwen3.5:9b")
    
    available = await provider.is_available()
    if not available:
        print("? Erreur : Ollama n'est pas accessible sur http://localhost:11434")
        return

    print("? Service Ollama en ligne.")
    print("Test de generation avec qwen3.5:9b...")
    
    try:
        response = await provider.generate(
            prompt="Dis 'ARENA est operationnel !' en une phrase courte.",
            system_prompt="Tu es l'assistant de test ARENA."
        )
        print(f"\n?? Reponse de l'IA locale :\n{response.strip()}\n")
        print("? TEST REUSSI !")
    except Exception as e:
        print(f"? Erreur lors de la generation : {e}")

if __name__ == "__main__":
    asyncio.run(main())
