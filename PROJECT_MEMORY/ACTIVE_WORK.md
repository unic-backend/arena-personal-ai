# TRAVAIL EN COURS

*Mise à jour : 2026-08-28, fin de session.*

## État à l'instant

| | |
|---|---|
| Branche | `claude/arena-personal-ai-integration-grp0ey` |
| PR ouverte | celle qui porte ce fichier — voir CHANGELOG.md |
| `master` | `45861a7` (**PR #21 fusionnée**, 4 commits) |
| Tests | 1615 hors ligne au vert, 21 `integration` désélectionnés |
| Lint | `ruff` propre |
| Orphelins | 110 modules, 82 atteints, **aucun module réel endormi** |

## Ce qui est fusionné dans `master` (PR #21, 2026-08-28)

1. `doctor.py` réécrit — il affirmait `[OK] venv actif` sans mesurer ;
2. **chapitre 9 — l'agenda** : créneaux libres, conflits, rendez-vous derrière confirmation ;
3. `doctor.py` lit les noms de variables dans le code (il réclamait `GMAIL_*` périmés) ;
4. **MoneyPrinterTurbo** branché sur l'agent vidéo.

## Ce qui attend une action du PROPRIÉTAIRE

| Sujet | Ce qu'il faut de lui |
|---|---|
| **`USMAN_API_KEY`** | la changer s'il n'est pas certain de l'avoir fait (runbook, étape 1) |
| **Purge de l'historique** | jamais autorisée. Plus urgente depuis que le dépôt est privé — sa décision |
| **`apps/pwa/server/`** | on le garde ou on le supprime ? 482 lignes, second serveur mort |
| **Identifiants Google** | 3 valeurs dans `.env` pour réveiller courrier + agenda |
| **MoneyPrinterTurbo** | `scripts/installer_moneyprinter.ps1`, puis `llm_provider = "ollama"` et une clé Pexels dans **leur** `config.toml` |
| **Mesures 7.2** | `python -m pytest -m integration` et `python scripts/mesurer_performances.py` sur son PC |

## Prochaine action recommandée

**Ne pas ouvrir une nouvelle phase du plan de soi-même.** Le propriétaire donne
la suite. Si elle vient : le plan pointe sur **11.1 — appels d'offres
sénégalais** (`docs/PLAN_ARENA_OS.md`), les chapitres 8, 9 et 10 étant terminés.

## Ce qui n'est PAS à faire

- relire le dépôt entier au début d'une session — cette mémoire existe pour ça ;
- refaire vérifier un système verrouillé « pour être sûr » ;
- marquer quoi que ce soit `100%` sans preuve, ni afficher un chiffre non mesuré ;
- toucher à `apps/pwa/` : l'interface n'a **jamais** été regardée.
