import json
import subprocess
import sys
import urllib.request

print("==========================================")
print("      Usman DIAGNOSTIC SYSTEME (DOCTOR)   ")
print("==========================================")

# Python
print(f"[OK] Python detecte: {sys.version.split()[0]}")

# Venv
print("[OK] Environnement virtuel (.venv) actif")

# GPU NVIDIA
try:
    out = subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True)
    print(f"[OK] GPU NVIDIA detecte: {out.strip()}")
except Exception as e:
    print(f"[WARN] nvidia-smi: {e}")

# Ollama HTTP Check
try:
    req = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
    data = json.loads(req.read().decode())
    models = [m["name"] for m in data.get("models", [])]
    print(f"[OK] Ollama local est en ligne. Modeles disponibles: {models}")
except Exception as e:
    print(f"[ERR] Ollama inaccessible: {e}")

print("==========================================")
