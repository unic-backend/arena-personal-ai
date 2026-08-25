import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.memory.memory_manager import MemoryManager
from agents.coder.coder_agent import CoderAgent

async def main():
    print("--- Test du CoderAgent Autonome (Qwen 2.5 Coder 14B) ---")
    
    # Utilisation du modèle local dédié au code
    coder_provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen2.5-coder:14b")
    memory = MemoryManager()
    
    agent = CoderAgent(provider=coder_provider, memory=memory)
    
    prompt = "Écris une fonction Python qui calcule la somme des nombres pairs de 1 à 100 et affiche le résultat avec print."
    res = await agent.run(prompt)
    
    print(f"Statut : {res['status']}")
    print(f"Auto-corrigé : {res.get('auto_corrected')}")
    print("\n" + res['response'])
    print("--- TEST CODER AGENT VALIDE AVEC SUCCES ---")

if __name__ == "__main__":
    asyncio.run(main())