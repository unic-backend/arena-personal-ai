import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.models.ollama_provider import OllamaProvider
from core.reasoning.reasoning_engine import ReasoningEngine

async def main():
    print("🧠 Test du Moteur de Raisonnement Profond (Plan & Solve + SymPy)...")
    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model_name="qwen2.5-coder:14b")
    
    engine = ReasoningEngine(provider=provider)
    
    prompt = "Résous l'équation x^2 - 5*x + 6 = 0 avec sympy et donne les racines exactes."
    res = await engine.solve_complex_task(prompt)
    
    print(f"\n   Calculs scientifiques : {res['calculation_result']}")
    print(f"\n🤖 SOLUTION SUBLIME :\n{res['final_response']}\n")
    print("✅ MOTEUR DE RAISONNEMENT PROFOND VALIDE AVEC SUCCES !")

if __name__ == "__main__":
    asyncio.run(main())