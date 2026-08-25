from pathlib import Path

# CHANGELOG.md
changelog_content = """# CHANGELOG - ARENA PERSONAL AI

## [0.9.3] - 2026-08-25
### Sécurité & Assainissement (Audit Claude Code)
- Assainissement strict de `file.filename` à l'upload pour éviter toute traversée de répertoire.
- Validation stricte des chemins `video_path` restreints au dossier `media/`.
- Intégration d'OpenSandbox (Bac à Sable Docker Isolé avec Fallback Averti).
- Rétablissement des routes `/api/chat` et `/api/chat/stream` pour compatibilité totale.
- Correction de la politique CORS FastAPI et chargement de `.env`.
- Ajout de `sympy` et `numpy` dans `requirements.txt`.

## [0.9.1] - 2026-08-25
### Ajouté
- Moteur de Raisonnement Profond (ReasoningEngine Plan & Solve avec SymPy).
- Intégration du CoderAgent autonome avec Qwen 2.5 Coder 14B.
- Streaming SSE pour des réponses en 4 secondes.
"""
Path("docs/CHANGELOG.md").write_text(changelog_content, encoding="utf-8")

# CURRENT_TASK.md
current_task_content = """# TÂCHE ACTUELLE
ID: TASK-000037
TÂCHE ACTUELLE : Bilan d'Audit & Sécurisation globale v0.9.3
OBJECTIF : Résolution intégrale de tous les points d'audit de Claude Code (Sécurité Upload, Sandbox, CORS, Docs).
ÉTAT : [x] TERMINÉ
PROCHAINE ACTION : Exécuter la suite de tests globale et réaliser le commit Git v0.9.3.
"""
Path("docs/CURRENT_TASK.md").write_text(current_task_content, encoding="utf-8")

print("✅ Documentation CHANGELOG.md et CURRENT_TASK.md synchronisées sous v0.9.3 !")