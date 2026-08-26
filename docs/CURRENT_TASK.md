# TÂCHE ACTUELLE

ID : TASK-000044
TÂCHE : Alignement post-fusion Studio + doc (rotation, tests, purge optionnelle)
ÉTAT : [x] EN COURS — point 1/4 (CURRENT_TASK)

## Où en est-on (mesuré / rechargé le 26/08/2026 soir)

Branche de travail : `travail` (push OK, dont fix `test_gitleaks_config.py`).

Livraisons majeures du 26/08/2026 :
- Phase 7 bis : sécu (auth, CORS, sandbox REFUSED, rate-limit, gitleaks CI)
- Backend découpé : `main.py` mince + routeurs + `studio.py`
- Info fraîche (sources + horloge système pour l’actualité)
- Indexation documentaire (lecture + inventaire + hors Git)
- Interface hors ligne (Tailwind local)
- Réunion branche **vidéo Usman** + branche **ingénierie** : Studio 1-clic,
  hardsub, Whisper — **sans** remettre les secrets en clair
- Tests (worklog fusion Studio) : montée jusqu’à **424** tests
- Notre correctif : `check-ignore` skip hors dépôt Git (Sprint A)

## Rotation de clé (propriétaire)

- [x] **Rotation** : nouvelle clé dans `.env` local (`USMAN_API_KEY`, compat
  `ARENA_API_KEY` encore lue par le code). L’ancienne ne doit plus servir en runtime.
- [ ] **Purge historique Git** : optionnelle. Anciennes valeurs encore possibles
  dans l’historique public. Voir `documents/RUNBOOK_PURGE_SECRETS.md`.
  Exécution **uniquement** avec accord explicite du propriétaire (irréversible).
- [ ] Supprimer la branche distante dangereuse si elle existe encore
  (`saer-video-wip` ou équivalent avec clé en clair) — après validation.

## Ce qui reste (ordre des 4 points)

1. [x] `docs/CURRENT_TASK.md` (ce fichier)
2. [ ] `docs/NEXT_STEPS.md`
3. [ ] `README.md` — standardiser `USMAN_API_KEY`
4. [ ] Purge / branche dangereuse (guidage) + mesures VRAM si demandé

## Règle

On ne coche qu’après vérification exécutée. Les chiffres de tests viennent du
worklog (`documents/USMAN_ENGINEERING_WORKLOG.md`) et des runs sur clone.