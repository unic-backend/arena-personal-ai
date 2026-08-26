# PROCHAINES ÉTAPES

*Mis à jour le 26/08/2026 (soir) — alignement après fusion Studio + rotation.*

La liste détaillée vit dans `documents/USMAN_ENGINEERING_WORKLOG.md`.
Voici l’ordre réel **maintenant**.

## 1. Clé API — **rotation faite** ; purge **optionnelle**

- [x] **Rotation** : nouvelle `USMAN_API_KEY` dans `.env` local (compat
  `ARENA_API_KEY` encore lue par le code si besoin). L’ancienne clé ne doit
  plus ouvrir la passerelle en runtime.
- [ ] **Purge de l’historique Git** : optionnelle. L’historique public peut
  encore contenir d’anciennes valeurs. Procédure :
  `documents/RUNBOOK_PURGE_SECRETS.md`.  
  **Accord explicite du propriétaire requis** (irréversible, force-push).
- [ ] Supprimer les branches distantes dangereuses si elles existent encore
  (ex. `saer-video-wip` avec clé en clair) — après validation.

Sans purge : le runtime est sûr **si** la rotation est effective ; le dépôt
n’est pas « historiquement clean ».

## 2. Scan de secrets en CI — **fait**

`gitleaks` est dans `.github/workflows/ci.yml` (job secrets + config
`.gitleaks.toml`). Un secret commité doit faire échouer la CI.

## 3. Mesurer avant d’optimiser (Phase 8)

Sur la machine Saer, **une commande à la fois**, recopier les sorties dans le
worklog :