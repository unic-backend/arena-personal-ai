# Usman IA PERSONNELLE — GUIDE DE DÉMARRAGE

## Rôle d'Usman
Usman est le cerveau principal et l'architecte du projet.

## Comment reprendre une session ?
1. **Lire `documents/USMAN_ENGINEERING_WORKLOG.md`** — c'est le carnet de bord
   permanent : ce qui est fait, ce qui reste, les problèmes ouverts, et la
   vérification qui justifie chaque affirmation.
2. Regarder l'état Git (`git status`, `git log --oneline -10`).
3. Lire `ROADMAP.md` et `CURRENT_TASK.md` pour le cadrage.
4. **Vérifier avant de croire** : une case cochée dans la documentation n'est pas
   une preuve que le code la respecte. Le worklog dit comment chaque point a été
   vérifié — sans mention de vérification, considérer le point comme ouvert.

## Vérifier que tout marche encore
```
pytest
ruff check .
```
Référence au 26/08/2026 : 148 tests verts, 17 désélectionnés, 0 erreur de lint.

## Statut initial
- Machine : Win11 / RTX A2000 (12 Go) / 32 Go RAM
- Stockage : C: (~32 Go libres)
- IA Locale : Ollama (qwen3.5:9b, qwen2.5-coder:14b)
