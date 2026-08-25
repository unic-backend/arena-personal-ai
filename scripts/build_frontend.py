import sys
from pathlib import Path

# 1. Création du fichier index.html
html_content = """<!DOCTYPE html>
<html lang="fr" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARENA — IA Personnelle Autonome</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        arena: {
                            50: '#f4f6ff',
                            100: '#e9edff',
                            500: '#6366f1',
                            800: '#1e1b4b',
                            900: '#0f172a',
                            950: '#020617',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        body { background-color: #090d16; color: #f1f5f9; font-family: system-ui, -apple-system, sans-serif; }
        .glass { background: rgba(15, 23, 42, 0.75); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); }
        .chat-scroll::-webkit-scrollbar { width: 6px; }
        .chat-scroll::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
    </style>
</head>
<body class="h-screen flex flex-col overflow-hidden">

    <!-- HEADER TOP BAR -->
    <header class="h-16 glass flex items-center justify-between px-6 border-b border-slate-800">
        <div class="flex items-center space-x-3">
            <div class="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></div>
            <h1 class="text-xl font-bold tracking-wider text-white">ARENA <span class="text-xs px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">CORE v0.1</span></h1>
        </div>
        <div class="flex items-center space-x-6 text-sm">
            <div class="flex items-center space-x-2 bg-slate-800/60 px-3 py-1.5 rounded-lg border border-slate-700/50">
                <span class="text-slate-400">Modèle Local:</span>
                <span id="model-badge" class="font-mono text-indigo-300 font-semibold">Chargement...</span>
            </div>
            <div class="flex items-center space-x-2 bg-slate-800/60 px-3 py-1.5 rounded-lg border border-slate-700/50">
                <span class="text-slate-400">GPU:</span>
                <span class="font-mono text-emerald-400 font-semibold">RTX A2000 (12GB)</span>
            </div>
            <div id="status-badge" class="px-3 py-1.5 rounded-lg font-medium text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                EN LIGNE
            </div>
        </div>
    </header>

    <!-- MAIN CONTAINER -->
    <div class="flex-1 flex overflow-hidden">
        
        <!-- SIDEBAR -->
        <aside class="w-72 glass border-r border-slate-800 flex flex-col justify-between p-4">
            <div class="space-y-6">
                <div>
                    <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Système & Agents</h2>
                    <nav class="space-y-1">
                        <a href="#" class="flex items-center justify-between px-3 py-2 rounded-lg bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 font-medium text-sm">
                            <span>💬 Console Orchestrateur</span>
                            <span class="w-2 h-2 rounded-full bg-indigo-400"></span>
                        </a>
                        <a href="#" class="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-slate-800/50 text-slate-400 hover:text-slate-200 text-sm transition">
                            <span>🎬 Pipeline Vidéo</span>
                            <span class="text-xs text-slate-500">Inactif</span>
                        </a>
                        <a href="#" class="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-slate-800/50 text-slate-400 hover:text-slate-200 text-sm transition">
                            <span>🌍 Recherche & Tendances</span>
                            <span class="text-xs text-slate-500">Inactif</span>
                        </a>
                    </nav>
                </div>

                <div>
                    <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Mémoire Opérationnelle</h2>
                    <div class="bg-slate-900/80 p-3 rounded-lg border border-slate-800 space-y-2 text-xs">
                        <div class="flex justify-between text-slate-400"><span>Mode:</span><span class="text-slate-200 font-mono">0 — CHAT</span></div>
                        <div class="flex justify-between text-slate-400"><span>Stockage C:</span><span class="text-emerald-400 font-mono">32.6 Go OK</span></div>
                        <div class="flex justify-between text-slate-400"><span>Agents actifs:</span><span class="text-indigo-400 font-mono">Orchestrator</span></div>
                    </div>
                </div>
            </div>

            <div class="border-t border-slate-800 pt-3 text-xs text-slate-500 text-center">
                ARENA Personal AI — Local First
            </div>
        </aside>

        <!-- CHAT AREA -->
        <main class="flex-1 flex flex-col bg-slate-950/40">
            <!-- MESSAGES CONTAINER -->
            <div id="chat-messages" class="flex-1 overflow-y-auto p-6 space-y-4 chat-scroll">
                <!-- Message d'accueil ARENA -->
                <div class="flex space-x-3 max-w-3xl">
                    <div class="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-xs shadow-lg shadow-indigo-500/20">A</div>
                    <div class="flex-1 bg-slate-900/90 border border-slate-800 rounded-2xl rounded-tl-none p-4 text-slate-200 text-sm leading-relaxed shadow-sm">
                        <p class="font-semibold text-indigo-400 mb-1">ARENA System</p>
                        Bonjour ! Je suis ARENA, ton IA personnelle local-first. Je fonctionne sur ta carte graphique RTX A2000 avec Qwen 3.5. Comment puis-je t'assister ?
                    </div>
                </div>
            </div>

            <!-- INPUT BOX -->
            <div class="p-4 glass border-t border-slate-800">
                <form id="chat-form" class="max-w-4xl mx-auto flex space-x-3">
                    <input type="text" id="user-input" autocomplete="off" placeholder="Pose une question ou donne une instruction à ARENA..." 
                        class="flex-1 bg-slate-900/90 border border-slate-700/80 rounded-xl px-4 py-3 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm">
                    <button type="submit" id="send-btn" class="bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-6 py-3 rounded-xl transition flex items-center space-x-2 text-sm shadow-lg shadow-indigo-600/20">
                        <span>Envoyer</span>
                    </button>
                </form>
            </div>
        </main>
    </div>

    <!-- JAVASCRIPT CONNECTIVITY -->
    <script>
        const chatMessages = document.getElementById('chat-messages');
        const chatForm = document.getElementById('chat-form');
        const userInput = document.getElementById('user-input');
        const sendBtn = document.getElementById('send-btn');
        const modelBadge = document.getElementById('model-badge');

        // Check Backend Health
        async function checkHealth() {
            try {
                const res = await fetch('/health');
                const data = await res.json();
                if(data.ollama_available) {
                    modelBadge.innerText = data.model;
                } else {
                    modelBadge.innerText = 'Ollama Hors-ligne';
                    modelBadge.classList.replace('text-indigo-300', 'text-red-400');
                }
            } catch(e) {
                modelBadge.innerText = 'Erreur Serveur';
            }
        }
        checkHealth();

        function appendMessage(sender, text, isUser = false) {
            const msgDiv = document.createElement('div');
            msgDiv.className = `flex space-x-3 max-w-3xl ${isUser ? 'ml-auto justify-end' : ''}`;
            
            if (!isUser) {
                msgDiv.innerHTML = `
                    <div class="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-xs shadow-lg shadow-indigo-500/20">A</div>
                    <div class="flex-1 bg-slate-900/90 border border-slate-800 rounded-2xl rounded-tl-none p-4 text-slate-200 text-sm leading-relaxed shadow-sm">
                        <p class="font-semibold text-indigo-400 mb-1">ARENA</p>
                        <div>${text}</div>
                    </div>
                `;
            } else {
                msgDiv.innerHTML = `
                    <div class="bg-indigo-600 text-white rounded-2xl rounded-tr-none p-4 text-sm leading-relaxed shadow-md">
                        ${text}
                    </div>
                `;
            }
            chatMessages.appendChild(msgDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = userInput.value.trim();
            if (!text) return;

            appendMessage('Moi', text, true);
            userInput.value = '';
            sendBtn.disabled = true;
            sendBtn.classList.add('opacity-50');

            // Indicateur de réflexion
            const loadingDiv = document.createElement('div');
            loadingDiv.id = 'loading-indicator';
            loadingDiv.className = 'flex space-x-3 max-w-3xl';
            loadingDiv.innerHTML = `
                <div class="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-xs">A</div>
                <div class="bg-slate-900 border border-slate-800 rounded-2xl rounded-tl-none p-4 text-slate-400 text-sm animate-pulse">
                    ARENA réfléchit...
                </div>
            `;
            chatMessages.appendChild(loadingDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: text })
                });
                const data = await res.json();
                document.getElementById('loading-indicator').remove();
                
                if (data.status === 'success') {
                    appendMessage('ARENA', data.response);
                } else {
                    appendMessage('ARENA', 'Erreur: ' + (data.detail || 'Impossible de répondre.'));
                }
            } catch(err) {
                document.getElementById('loading-indicator')?.remove();
                appendMessage('ARENA', 'Erreur de connexion au serveur backend.');
            } finally {
                sendBtn.disabled = false;
                sendBtn.classList.remove('opacity-50');
            }
        });
    </script>
</body>
</html>
"""

Path("apps/frontend/index.html").write_text(html_content, encoding="utf-8")
print("✅ Interface Web créée dans apps/frontend/index.html !")

# 2. Mise à jour de apps/backend/main.py pour servir l'interface web à la racine
main_py_content = """import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from core.models.ollama_provider import OllamaProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/backend.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("arena.backend")

app = FastAPI(title="ARENA Personal AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

provider = OllamaProvider(model_name=os.getenv("DEFAULT_LOCAL_MODEL", "qwen3.5:9b"))

class ChatRequest(BaseModel):
    prompt: str
    system_prompt: Optional[str] = "Tu es ARENA, le cerveau et chef de projet de mon IA personnelle."

class ChatResponse(BaseModel):
    status: str
    model: str
    response: str

@app.get("/")
async def serve_frontend():
    return FileResponse("apps/frontend/index.html")

@app.get("/health")
async def health_check():
    ollama_online = await provider.is_available()
    return {
        "status": "healthy" if ollama_online else "degraded",
        "ollama_available": ollama_online,
        "model": provider.model_name
    }

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if not await provider.is_available():
        raise HTTPException(status_code=503, detail="Le modèle local Ollama n'est pas disponible.")
    
    try:
        reply = await provider.generate(prompt=request.prompt, system_prompt=request.system_prompt)
        return ChatResponse(
            status="success",
            model=provider.model_name,
            response=reply.strip()
        )
    except Exception as e:
        logger.error(f"Erreur génération chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
"""

Path("apps/backend/main.py").write_text(main_py_content, encoding="utf-8")
print("✅ apps/backend/main.py mis à jour pour intégrer l'interface web !")
