# JOURNAL DES CHANGEMENTS — mémoire de session

*Ce que chaque session a réellement livré, avec sa preuve. Le récit complet vit
dans `docs/REPRISE.md` ; ici, l'essentiel pour reprendre sans tout relire.*

---

## 2026-08-28 — session « réveil, sécurité, chapitres 8 et 9, MoneyPrinterTurbo »

### Livré et fusionné

| PR | Ce qui change | Preuve |
|---|---|---|
| **#15** | la vidéo à l'agent vidéo, les documents au chemin documentaire (`suivi_video`, `travaux`, `indexer`, `inventory`) | 68 → 72 modules atteints |
| **#16** | la mémoire du chat : le sens (`semantique`) et une chose dite une fois (`consolidation`) | 72 → 74 |
| **#17** | le coût d'une réponse (`voies`, `mesures`) et un raisonnement qui calcule vraiment (`reasoning_engine`) ; `GET /api/observability` | 74 → 77, **0 module réel endormi** |
| **#18** | **sécurité** : LibreChat et Open WebUI retirés — 4 des 5 clés fuitées deviennent mortes (DEC-0007) | 2 sabotages |
| **#19** | le dépôt est passé **privé** par le propriétaire ; documents mis à jour | `"private": true` vérifié |
| **#20** | **chapitre 8** : courrier — lire, trier, et n'envoyer qu'avec son accord | 1462 → 1520 tests |

| **#21** | 4 commits : `doctor.py` qui mesure ; **chapitre 9 — agenda** ; `doctor.py` qui lit les noms dans le code ; **MoneyPrinterTurbo** sur l'agent vidéo | fusionnée en `45861a7` |

Mesure finale de la session : `ruff` propre, **1615 passed / 21 deselected**,
110 modules, 82 atteints, aucun module réel endormi.

### Pièges trouvés par les tests, pas par relecture

- « fais-moi une vidéo sur les cloisons BA13 » partait chez l'assistant **devis** (le mot « ba13 » l'emportait) ;
- « suis-je libre **cette semaine** ? » partait chercher l'**actualité** sur le web ;
- « écris un mail au client » devait **rester** au métier, et y est resté (test du propriétaire du 27/08) ;
- « génère » porte un accent **grave** que `[ée]` ne couvrait pas ;
- `doctor.py` réclamait `GMAIL_CLIENT_ID` quand le projet attend `GOOGLE_CLIENT_ID`.

### Sabotages de la session

24 garanties cassées volontairement, 24 fois un test précis est tombé, toutes
restaurées. Les plus parlantes : « l'agent envoie sans confirmation » fait passer
le statut de `NEEDS_CONFIRMATION` à **`SUCCESS`** — le message part vraiment.

---

## 2026-08-28 (fin) — mise en place de PROJECT_MEMORY

Créé après la fusion de la PR #21 : ce dossier arrive donc dans une pull
request qui lui est propre. Création de `PROJECT_MEMORY/` (8 fichiers) sur
demande du propriétaire :
carte, architecture, systèmes achevés, travail en cours, zones verrouillées,
dépendances, index des décisions, ce journal.

**Aucun code applicatif modifié.** Aucun système marqué `100%` sans preuve : la
distinction « logique vérifiée » / « bout en bout » est posée explicitement dans
`COMPLETED_SYSTEMS.md`, parce que rien de ce qui dépend d'Ollama, de ffmpeg, de
Docker ou de Google n'a jamais tourné sur la machine de l'assistant.
