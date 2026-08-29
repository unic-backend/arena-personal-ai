# TRAVAIL EN COURS

*Mise à jour : 2026-08-29, fin de session.*

## État à l'instant

| | |
|---|---|
| Branche | `claude/arena-personal-ai-integration-grp0ey` (repartie de `master` à chaque PR fusionnée en cours de session — voir CHANGELOG.md) |
| `master` | PR #26 à #31 fusionnées, DEC-0015 (Hell-Grind-AIGC-Skill) prête à pousser |
| Tests | **1972** hors ligne au vert, 21 `integration` désélectionnés |
| Lint | `ruff` propre |
| Orphelins | 130 modules, 103 atteints, 27 orphelins — **tous** `__init__.py` vides. Aucun module réel endormi (`apps/pwa/server/` supprimé le 29/08/2026) |

## Ce qui vient de se fermer (PR #26 → #31, ce chunk)

| PR | Ce qui change | Statut |
|---|---|---|
| **#27** | `core/guardian/` — DÉCOUVRE et RAPPORTE (jamais MODIFIE), DEC-0014 | **FERMÉ** — 25 tests unitaires + 6 API, scénario §27 bout en bout |
| **#28** | correctif : `verifier_gardien()` distinguait mal « jamais lancé » de « lancé, rien trouvé » | **FERMÉ** — sabotage/restauration prouvés, +5 tests |
| **#29** | doc seule : la recherche web reste `UNKNOWN` en cloud à cause d'un 403 du bac à sable, pas seulement d'Ollama absent | **FERMÉ** — aucun code touché |
| **#30** | `apps/pwa/server/` supprimé (4 fichiers, 482 lignes) — décidé par le propriétaire depuis son téléphone | **FERMÉ** — 27 orphelins restants, tous `__init__.py` vides |
| **#31** | correctif interface : `.writing-text` (composeur + édition) invisible en mode clair | **FERMÉ** — build Vite réel vérifié, reste un `npm run build` chez lui |
| *(suivante)* | DEC-0015 — `tools/video/prompt_audit.py` + `VideoAnalyzerAgent.planifier_scene()`, premier appelant réel de `wan2gp` | **FERMÉ** — 35 tests (+20 audit, +15 branchement), sabotage prouvé |

Mesures 7.2 (phase entière) : **toujours `UNKNOWN`**, structurellement — ne pas
retenter depuis le cloud (Ollama absent, recherche web bloquée par la
politique réseau du bac à sable). Attend son PC, raison déjà écrite dans
`docs/REPRISE.md`.

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

## Ce qui est fusionné dans `master` depuis le 28/08/2026 (PR #21 → #31)

1. `doctor.py` réécrit, puis relié à `sonder()` de chaque connecteur (jamais une seconde logique de santé) ;
2. **chapitre 9 — l'agenda**, **MoneyPrinterTurbo** branché sur l'agent vidéo ;
3. **ARENA hybride (DEC-0009)** : confidentialité 4 niveaux, Groq + DeepInfra, aiguilleur, banc d'essai ;
4. **Réseaux sociaux actifs (DEC-0010)** : méthode extraite de `charlie947/social-media-skills`, rien copié ;
5. **Coordination des tâches (DEC-0011)** : `grok-bot-0.18-reconstructed` refusé (aucune licence) ; `core/execution/coordination.py` écrit sans emprunt ;
6. **OpenTakeoff — métré de plan PDF (DEC-0012)** : transport MCP stdio, sous-ensemble réel, la limite plafond/mur/rampant corrigée sur indication du propriétaire ;
7. **Crochets d'exécution + disjoncteur (DEC-0013)** : idée extraite de DeepSeek Harness (Cordis refusé), premier consommateur réel — coupe court après des échecs consécutifs réels sur un service tombé ;
8. **Gardien de maintenance (DEC-0014)** : idée extraite de live-swe-agent (aucun code d'agent trouvé, refusé) — DÉCOUVRE et RAPPORTE seulement, jamais MODIFIE (commit/PR autonome explicitement hors périmètre, contraire à la règle non négociable du projet) ; correctif ultérieur pour que `doctor.py` distingue « jamais lancé » de « lancé, rien trouvé » ;
9. `apps/pwa/server/` supprimé (décision du propriétaire) ; correctif `.writing-text` invisible en mode clair sur l'interface ;
10. **Hell-Grind-AIGC-Skill (DEC-0015)** : `tools/video/prompt_audit.py` (audit déterministe de prompt, méthode extraite) + `VideoAnalyzerAgent.planifier_scene()` — premier appelant réel de `wan2gp.generer`, jamais invoqué si l'audit trouve une erreur bloquante.

## Ce qui attend une action du PROPRIÉTAIRE

| Sujet | Ce qu'il faut de lui |
|---|---|
| **`USMAN_API_KEY`** | la changer s'il n'est pas certain de l'avoir fait (runbook, étape 1) |
| **Purge de l'historique** | jamais autorisée. Le dépôt est privé — sa décision |
| **Identifiants Google** | 3 valeurs dans `.env` pour réveiller courrier + agenda |
| **MoneyPrinterTurbo** | `scripts/installer_moneyprinter.ps1`, puis `llm_provider = "ollama"` et une clé Pexels dans **leur** `config.toml` |
| **OpenTakeoff** | `scripts/installer_opentakeoff.ps1`, puis `OPENTAKEOFF_MCP_DIR` dans `.env` — vérifié bout en bout dans cette session (ci-dessus), il ne reste que le geste chez lui |
| **Interface (PWA)** | `npm run build` dans `apps/pwa/` pour que le correctif du mode clair (PR #31) serve réellement |
| **WanGP** | lancer `python wgp.py --mcp --mcp-transport streamable-http ...` pour que `planifier_scene` (DEC-0015) génère vraiment une scène |
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
