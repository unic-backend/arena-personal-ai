# TÂCHE ACTUELLE

ID : TASK-000042
TÂCHE : Phase 7 bis — correction après les quatre rapports d'audit du 26/08/2026
ÉTAT : [ ] EN COURS

## Où en est-on

12 correctifs livrés sur la branche `claude/arena-personal-ai-qh66ix`, chacun
avec sa vérification. Détail complet : `documents/ARENA_ENGINEERING_WORKLOG.md`.

État mesuré le 26/08/2026 :
- `pytest` → 148 tests verts, 17 marqués `integration`
- `ruff check .` → 0 erreur
- 12 commits, contre 1 au départ

## Ce qui reste, et bloque

**Un seul point critique** : la clé API est encore lisible dans l'historique Git
du dépôt public. La rotation et la purge demandent une décision du propriétaire —
la purge est irréversible.

## Correction d'une entrée précédente

TASK-000041 déclarait « 15 défauts identifiés, **tous vérifiés par un test** ».
La vérification a montré que ce n'était pas le cas : trois livrables de la
Phase 7 n'étaient pas effectifs, et dix fichiers de tests sur 21 n'étaient même
pas collectés par pytest.

Ce n'est pas un reproche sur le travail fourni — c'est la raison d'être de la
règle posée en tête de `ROADMAP.md` : **on ne coche qu'après avoir exécuté la
vérification.**
