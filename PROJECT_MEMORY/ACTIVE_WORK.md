# TRAVAIL EN COURS

*Mise à jour : 2026-08-29, fin de session.*

## État à l'instant

| | |
|---|---|
| Branche | `claude/arena-personal-ai-integration-grp0ey` (repartie de `master` à chaque PR fusionnée en cours de session — voir CHANGELOG.md) |
| `master` | `b672849` (**PR #25 fusionnée**) — PR #22 à #25 toutes fusionnées cette session |
| Tests | **1899** hors ligne au vert, 21 `integration` désélectionnés |
| Lint | `ruff` propre |
| Orphelins | 128 modules, 98 atteints, 30 orphelins (voir `docs/CURRENT_TASK.md` pour ce qui est nommément accepté — `__init__.py` vides et `apps/pwa/server/`) |

## Diagnostic machine (`doctor.py`), mesuré le 29/08/2026

Sur la machine de l'assistant (cloud, sans Ollama/Docker/ffmpeg/GPU — jamais
présents ici) :

```
[OK]   Python                   version 3.11.15
[ABS]  Environnement virtuel    aucun venv actif
[ABS]  Dependances              1 paquet manquant : uvicorn
[CONF] Cle API                  USMAN_API_KEY absente
[OK]   Inference (hybride)      mode HYBRIDE, tout passe par Ollama
[PANNE] Ollama / Modele rapide / Modele profond / Modele d'embeddings
[ABS]  Carte graphique / ffmpeg (video) / Docker (bac a sable)
[CONF] WanGP (generation video) / Video courte (MPT)
[CONF] Metre de plan (OpenTakeoff)  OPENTAKEOFF_MCP_DIR absent ou dist/server.js introuvable
[CONF] Courrier (Gmail) / Agenda (Calendar)  identifiants Google absents
[OK]   Connaissances metier     31 article(s) tarifes
[ABS]  Documents                dossier vide
```

**La ligne `Metre de plan (OpenTakeoff)` a été vérifiée BOUT EN BOUT** :
OpenTakeoff construit une fois dans cette session (`node`, `npm install`,
`npm run build`, hors dépôt), `OPENTAKEOFF_MCP_DIR` pointé dessus →

```
[OK]   Metre de plan (OpenTakeoff) OpenTakeoff repond : 42 outil(s) annonce(s).
```

`11 capacité(s) indisponible(s)` au lieu de 12. C'est exactement ce que
`scripts/installer_opentakeoff.ps1` produit chez le propriétaire (Windows) —
mesuré ici, jamais supposé. Le reste (Ollama, Docker, WanGP, MoneyPrinterTurbo,
Gmail/Agenda) reste `[ABS]`/`[CONF]`/`[PANNE]` sur cette machine, comme
attendu : rien de tout ça n'y a jamais été installé.

## Ce qui est fusionné dans `master` depuis le 28/08/2026 (PR #21 → #25)

1. `doctor.py` réécrit, puis relié à `sonder()` de chaque connecteur (jamais une seconde logique de santé) ;
2. **chapitre 9 — l'agenda**, **MoneyPrinterTurbo** branché sur l'agent vidéo ;
3. **ARENA hybride (DEC-0009)** : confidentialité 4 niveaux, Groq + DeepInfra, aiguilleur, banc d'essai ;
4. **Réseaux sociaux actifs (DEC-0010)** : méthode extraite de `charlie947/social-media-skills`, rien copié ;
5. **Coordination des tâches (DEC-0011)** : `grok-bot-0.18-reconstructed` refusé (aucune licence) ; `core/execution/coordination.py` écrit sans emprunt ;
6. **OpenTakeoff — métré de plan PDF (DEC-0012)** : transport MCP stdio, sous-ensemble réel, la limite plafond/mur/rampant corrigée sur indication du propriétaire ;
7. **Crochets d'exécution + disjoncteur (DEC-0013)** : idée extraite de DeepSeek Harness (Cordis refusé), premier consommateur réel — coupe court après des échecs consécutifs réels sur un service tombé.

## Ce qui attend une action du PROPRIÉTAIRE

| Sujet | Ce qu'il faut de lui |
|---|---|
| **`USMAN_API_KEY`** | la changer s'il n'est pas certain de l'avoir fait (runbook, étape 1) |
| **Purge de l'historique** | jamais autorisée. Plus urgente depuis que le dépôt est privé — sa décision |
| **`apps/pwa/server/`** | on le garde ou on le supprime ? 482 lignes, second serveur mort |
| **Identifiants Google** | 3 valeurs dans `.env` pour réveiller courrier + agenda |
| **MoneyPrinterTurbo** | `scripts/installer_moneyprinter.ps1`, puis `llm_provider = "ollama"` et une clé Pexels dans **leur** `config.toml` |
| **OpenTakeoff** | `scripts/installer_opentakeoff.ps1`, puis `OPENTAKEOFF_MCP_DIR` dans `.env` — vérifié bout en bout dans cette session (ci-dessus), il ne reste que le geste chez lui |
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
