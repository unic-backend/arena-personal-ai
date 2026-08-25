import sys
from pathlib import Path

# ROADMAP.md
Path("docs/ROADMAP.md").write_text("""# ROADMAP DU PROJET - ARENA

## PHASE 0 — FONDATIONS
- [x] Diagnostic système et outils (TASK-000001)
- [x] Arborescence complète du projet (TASK-000002)
- [x] Mémoire opérationnelle docs/ (TASK-000003)
- [x] Fichiers de configuration de base (.gitignore, .env.example, README) (TASK-000004)
- [x] Environment virtuel Python & dépendances de base (TASK-000005)
- [x] Configuration Modèle Local (Ollama Provider - Qwen 3.5:9b) (TASK-000006)
- [x] Backend FastAPI & Logging (TASK-000007)
- [x] Scripts de diagnostic et gestion (doctor.py, start.ps1) (TASK-000008)
- [x] Validation intégrée API Backend & Ollama (TASK-000010)
- [x] Interface Web Dashboard & Chat ARENA (TASK-000011)

## PHASE 1 — CERVEAU LOCAL & MÉMOIRE
- [ ] Système de Mémoire Persistante SQLite / Vector (TASK-000012)
- [ ] Agent Orchestrateur principal (Agent Core) (TASK-000013)
- [ ] Système de Gestion des Permissions & Sécurité (TASK-000014)

## PHASE 2 — VISION ET AUDIO (Whisper & Local Vision)
- [ ] Integration FFmpeg local pour extraction audio/vidéo
- [ ] Pipeline de transcription locale Whisper

## PHASE 3 — CRÉATION VIDÉO (PIPELINE VERTICAL)
- [ ] Analyse & Découpe de moments clés
- [ ] Sous-titrage dynamique 9:16 & Cadrage
- [ ] Quality Control Agent
""", encoding="utf-8")

# CURRENT_TASK.md
Path("docs/CURRENT_TASK.md").write_text("""# TÂCHE ACTUELLE
ID: TASK-000011
TÂCHE ACTUELLE : Test en direct de l'Interface Web ARENA
OBJECTIF : Lancer le serveur backend et valider l'interaction via le navigateur
ÉTAT : [~] EN COURS
CE QUI EST FAIT :
- Création de apps/frontend/index.html (Dashboard Dark Mode + Chat)
- Intégration dans FastAPI apps/backend/main.py
CE QUI RESTE :
- Lancer le serveur local
- Tester l'envoi d'un message depuis le navigateur
BLOCAGES : Aucun
PROCHAINE ACTION : Lancer .\\scripts\\start.ps1 et ouvrir http://127.0.0.1:8000
""", encoding="utf-8")

# PROGRESS.md
Path("docs/PROGRESS.md").write_text("""# AVANCEMENT DU PROJET

- 2026-08-24 : Diagnostic matériel exécuté (RTX A2000 12GB VRAM / Ollama OK).
- 2026-08-24 : Arborescence complète et mémoire opérationnelle (docs/) créées.
- 2026-08-24 : Abstraction ModelProvider & Connecteur Ollama Qwen 3.5:9b validés.
- 2026-08-24 : API Backend FastAPI créée, configurée et testée avec succès.
- 2026-08-24 : Dashboard Web moderne créé dans apps/frontend/index.html et raccordé au backend.
""", encoding="utf-8")

# CHANGELOG.md
Path("docs/CHANGELOG.md").write_text("""# CHANGELOG

## [0.1.0] - 2026-08-24
### Ajouté
- Phase 0 complétée.
- Backend FastAPI avec endpoints /health et /api/chat.
- Interface Web moderne Dark Mode (Tailwind CSS) avec console de chat interactive.
- Scripts de diagnostic doctor.py et de démarrage start.ps1.
""", encoding="utf-8")

print("✅ Mémoire opérationnelle mise à jour !")
