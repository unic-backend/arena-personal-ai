from pathlib import Path

# ROADMAP.md
Path("docs/ROADMAP.md").write_text("""# ROADMAP AUTOMATIQUE DU PROJET - ARENA

## PHASE 0 — FONDATIONS [TERMINÉ]
- [x] Diagnostic matériel & outils
- [x] Arborescence unifiée
- [x] Environment virtuel & dépendances
- [x] Provider IA Local Ollama Qwen 3.5:9b sur RTX A2000
- [x] Backend FastAPI & Interface Web Dashboard

## PHASE 1 — CERVEAU LOCAL & SÉCURITÉ [TERMINÉ]
- [x] Mémoire Persistante SQLite memory.db
- [x] Reconnaissance du Propriétaire (Saer)
- [x] PermissionManager & Sécurité

## PHASE 2 — MOTEUR D'AUTONOMIE & CODE INTERPRETER [TERMINÉ]
- [x] CodeInterpreterTool (Exécution sécurisée de Python en local)
- [x] CoderAgent autonome avec Qwen 2.5 Coder 14B & auto-correction
- [x] Intégration Multi-Modèles (Qwen 3.5 + Qwen 2.5 Coder 14B)

## PHASE 3 — VISION, AUDIO & VIDÉO VERTICALE 9:16 [TERMINÉ]
- [x] FFmpeg local & CropTool (Reformatage 1080x1920)
- [x] Faster-Whisper local (Transcription)
- [x] SubtitleTool & SubtitleAgent (.srt automatiques)
- [x] VideoAnalyzerAgent & EditorAgent

## PHASE 4 — RECHERCHE & TENDANCES [TERMINÉ]
- [x] WebSearchTool local sans clé d'API
- [x] TrendAnalyzerAgent (Sénégal, Afrique, Monde)

## PHASE 5 — PERSPECTIVES ET SUITE [EN COURS]
- [ ] Agent Deep Research avancé (Kimi / Perplexity Pattern)
- [ ] Interface Web avec lecteur vidéo & gestion des fichiers
- [ ] Expansion des fonctionnalités Sénégal / Afrique
""", encoding="utf-8")

# CURRENT_TASK.md
Path("docs/CURRENT_TASK.md").write_text("""# TÂCHE ACTUELLE
ID: TASK-000029
TÂCHE ACTUELLE : Définition du prochain objectif majeur avec Saer
OBJECTIF : Choisir entre l'Agent Deep Research, le lecteur vidéo Web ou un sous-module spécifique.
ÉTAT : [~] EN COURS
PROCHAINE ACTION : Valider la prochaine priorité avec Saer.
""", encoding="utf-8")

print("✅ Documentation de la Task 28 synchronisée avec succès !")