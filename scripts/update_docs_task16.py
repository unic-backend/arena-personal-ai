import sys
from pathlib import Path

# ROADMAP.md
Path("docs/ROADMAP.md").write_text("""# ROADMAP DU PROJET - ARENA

## PHASE 0 — FONDATIONS
- [x] Diagnostic système et outils (TASK-000001)
- [x] Arborescence complète du projet (TASK-000002)
- [x] Mémoire opérationnelle docs/ (TASK-000003)
- [x] Fichiers de configuration racine (.gitignore, .env.example, README) (TASK-000004)
- [x] Environment virtuel Python & dépendances (TASK-000005)
- [x] Provider IA local Ollama Qwen 3.5:9b (TASK-000006)
- [x] Backend FastAPI & Logging (TASK-000007)
- [x] Scripts de diagnostic doctor.py (TASK-000008)
- [x] Interface Web Dashboard & Chat Interactive (TASK-000011)

## PHASE 1 — CERVEAU LOCAL & MÉMOIRE PERSISTANTE
- [x] Gestionnaire de Mémoire Persistante SQLite (TASK-000012)
- [x] Injection de Contexte & Reconnaissance du Propriétaire (Saer) (TASK-000013)
- [x] Architecture de base des Agents (BaseAgent) (TASK-000014)
- [x] Agent Orchestrateur Principal & Raccordement Backend (TASK-000015)
- [ ] Système de Permissions & Sécurité des actions (TASK-000016)

## PHASE 2 — VISION & AUDIO (LOCAL)
- [ ] Integration FFmpeg local pour extraction médias
- [ ] Pipeline de transcription locale (Whisper local)

## PHASE 3 — CRÉATION VIDÉO (PIPELINE VERTICAL)
- [ ] Analyse & Découpe automatique d'extraits
- [ ] Génération de sous-titres 9:16
- [ ] Quality Control Agent
""", encoding="utf-8")

# CURRENT_TASK.md
Path("docs/CURRENT_TASK.md").write_text("""# TÂCHE ACTUELLE
ID: TASK-000016
TÂCHE ACTUELLE : Système de Permissions et Sécurité
OBJECTIF : Créer le gestionnaire de permissions (READ_FILES, WRITE_FILES, EXECUTE_COMMANDS, PUBLISH) pour encadrer le fonctionnement des agents
ÉTAT : [~] EN COURS
CE QUI EST FAIT :
- Agent Orchestrateur Principal raccordé à l'API et à l'interface Web
- Mémoire SQLite persistante active
CE QUI RESTE :
- Implémenter core/permissions/permission_manager.py
- Créer la configuration des droits par défaut dans config/permissions.yaml
- Tester le contrôle des permissions
BLOCAGES : Aucun
PROCHAINE ACTION : Implémenter le gestionnaire de permissions
""", encoding="utf-8")

# PROGRESS.md
Path("docs/PROGRESS.md").write_text("""# AVANCEMENT DU PROJET

- 2026-08-24 : Phase 0 complétée.
- 2026-08-24 : Mémoire SQLite & Reconnaissance de Saer validées.
- 2026-08-24 : BaseAgent et OrchestratorAgent créés, raccordés à l'API backend et à l'interface web.
""", encoding="utf-8")

print("✅ Documentation mise à jour pour TASK-000016 !")