# CHANGELOG - ARENA PERSONAL AI

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
