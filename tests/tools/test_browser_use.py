import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.browser.browser_use_tool import BrowserUseTool

async def test_browser_use():
    print("🌐 Test de la navigation autonome Browser-Use + Playwright...")
    tool = BrowserUseTool()

    task = "Visite https://example.com et extrait le titre principal de la page."
    print(f"   Instruction : '{task}'")
    
    res = await tool.run_task(task)

    print(f"   Statut : {res['status']}")
    print(f"   Résultat obtenu : {res['result']}")
    print("✅ TEST BROWSER-USE COMPLÉTÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    asyncio.run(test_browser_use())