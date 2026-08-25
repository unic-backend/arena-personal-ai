import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from apps.backend.main import app

client = TestClient(app)

print("🔍 Test de diagnostic du Chat avec Mémoire...")
try:
    response = client.post("/api/chat", json={"prompt": "Comment je m'appelle ?", "session_id": "default"})
    print(f"Status Code: {response.status_code}")
    print(f"Réponse: {response.json()}")
except Exception as e:
    import traceback
    print("❌ ERREUR DÉTECTÉE :")
    traceback.print_exc()