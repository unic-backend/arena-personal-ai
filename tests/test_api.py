import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from apps.backend.main import app

client = TestClient(app)

def test_api():
    print("\n🔍 1. Test de l'endpoint /health...")
    res = client.get("/health")
    print(f"   Status Code: {res.status_code}")
    print(f"   Payload: {res.json()}")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    print("   ✅ Endpoint /health OK !")

    print("\n🔍 2. Test de l'endpoint /api/chat avec Ollama...")
    payload = {"prompt": "Confirme que l'API ARENA est fonctionnelle en une phrase courte."}
    res = client.post("/api/chat", json=payload)
    print(f"   Status Code: {res.status_code}")
    data = res.json()
    print(f"   Modèle utilisé: {data.get('model')}")
    print(f"   Réponse IA: {data.get('response')}")
    assert res.status_code == 200
    assert data["status"] == "success"
    print("   ✅ Endpoint /api/chat OK !")

    print("\n🎉 TOUS LES TESTS BACKEND SONT REUSSIS avec succes !\n")

if __name__ == "__main__":
    test_api()
