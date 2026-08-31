# TRAVAIL EN COURS

*Mise à jour : 2026-08-29, fin de session.*

## ⚠️ Ce fichier est périmé au-delà de PR #34

Plus de 40 PR sont passées depuis (DEC-0020 à DEC-0024 au moins, jusqu'à
`docs/DECISIONS.md`). Ce fichier n'a pas été réécrit à chaque fois — le
faire correctement exige de relire chaque PR fusionnée depuis, hors
périmètre d'une seule session. **Dernier chunk réellement documenté ici et
à jour : DEC-0024 (31/08/2026), connecteurs Gmail réels — voir
`docs/audits/connecteurs_audit.md` et l'entrée DEC-0024.** Pour tout le
reste, `docs/DECISIONS.md` (toutes les entrées) reste la source exacte ; ce
fichier est un index, pas l'autorité.

## État à l'instant (2026-08-29 — voir l'avertissement ci-dessus)

| | |
|---|---|
| Branche | `claude/arena-personal-ai-integration-grp0ey` (repartie de `master` à chaque PR fusionnée en cours de session — voir CHANGELOG.md) |
| `master` | PR #26 à #34 fusionnées (DEC-0019, Qwen3-VL) ; DEC-0020 (diagnostic/réparation) prête à pousser |
| Tests | **2011** hors ligne au vert, 21 `integration` désélectionnés (+5 depuis DEC-0020) |
| Lint | `ruff` propre |
| Orphelins | 132 modules, 104 atteints, 28 orphelins — **tous** `__init__.py` vides. Aucun module réel endormi (`apps/pwa/server/` supprimé le 29/08/2026) |

## Dernier chunk : DEC-0020 — diagnostic et réparation, pas de nouvelle capacité

Mission demandée le 29/08/2026 : auditer la dette technique laissée par les
missions précédentes (silences avalés, fuites de ressources, frontières
entre composants, sécurité) et **réparer**, pas ajouter. Détail complet :
`docs/DECISIONS.md` DEC-0020.

Trois défauts confirmés et corrigés, chacun sabote-puis-restauré :
1. `agents/plaquiste/plaquiste_agent.py` — un chemin de plan pouvait
   désigner un fichier du dépôt d'ARENA lui-même (`.env`,
   `config/unic_plaquiste.yaml`) avant d'atteindre OpenTakeoff. Corrigé par
   `chemin_hors_du_depot()`, un contrôle de contention.
2. `core/execution/travaux.py` — l'historique des travaux **finis**
   grossissait sans fin (seul le parallélisme était borné). Corrigé par
   `TRAVAUX_TERMINES_GARDES = 200` + `_purger_les_anciens()`.
3. `core/models/ollama_provider.py` — une ligne de flux Ollama illisible
   disparaissait sans aucune trace (`except Exception: pass`). Corrigé par
   un `logger.debug()`.

Le reste de l'audit (≈50 `except Exception` du dépôt relus un par un,
cycle de vie httpx/MCP, TODO/FIXME/XXX, `shell=True`/`eval`/`exec`/
`pickle`, l'intégration Qwen3-VL relue au niveau du code) n'a rien trouvé
de plus — déjà correct. **Ne pas rouvrir ces composants "pour être sûr"** :
c'est exactement ce que la règle du projet interdit.

## Ce qui s'est fermé avant (PR #26 → #33)

| PR | Ce qui change | Statut |
|---|---|---|
| **#27** | `core/guardian/` — DÉCOUVRE et RAPPORTE (jamais MODIFIE), DEC-0014 | **FERMÉ** — 25 tests unitaires + 6 API, scénario §27 bout en bout |
| **#28** | correctif : `verifier_gardien()` distinguait mal « jamais lancé » de « lancé, rien trouvé » | **FERMÉ** — sabotage/restauration prouvés, +5 tests |
| **#29** | doc seule : la recherche web reste `UNKNOWN` en cloud à cause d'un 403 du bac à sable, pas seulement d'Ollama absent | **FERMÉ** — aucun code touché |
| **#30** | `apps/pwa/server/` supprimé (4 fichiers, 482 lignes) — décidé par le propriétaire depuis son téléphone | **FERMÉ** — 27 orphelins restants, tous `__init__.py` vides |
| **#31** | correctif interface `.writing-text` (mode clair) + DEC-0015 (audit de prompt WanGP) + DEC-0016 (Spec Kit refusé) — bundlées, PR fusionnée avant que chaque commit ait sa propre PR | **FERMÉ** — 35 tests, sabotage prouvé |
| **#32** | DEC-0017 — Agent-Reach refusé (sonde/installateur, rien à intégrer) ; `DeepResearcherAgent` corrigé : 3 recherches en séquence → en parallèle | **FERMÉ** — +1 test, sabotage (0,90 s séquentiel → 0,35 s parallèle) |
| **#33** | DEC-0018 — consolidation des modèles auditée, rien à fusionner (doc seule) | **FERMÉ** — aucun code touché |
| *(suivante)* | DEC-0019 — Qwen3-VL : `agents/vision/vision_agent.py`, intention `VISION`, `OllamaProvider.generate(images=...)`, pièces jointes image (jpg/png/webp/gif) | **FERMÉ** — 33 tests, 2 sabotages |

Mesures 7.2 (phase entière) : **toujours `UNKNOWN`**, structurellement — ne pas
retenter depuis le cloud (Ollama absent, recherche web bloquée par la
politique réseau du bac à sable). Attend son PC, raison déjà écrite dans
`docs/REPRISE.md`. La vision (DEC-0019) attend la même chose : `qwen3-vl:4b`
n'a jamais tourné, aucune image réelle n'a été analysée.

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

## Ce qui est fusionné dans `master` depuis le 28/08/2026 (PR #21 → #33)

1. `doctor.py` réécrit, puis relié à `sonder()` de chaque connecteur (jamais une seconde logique de santé) ;
2. **chapitre 9 — l'agenda**, **MoneyPrinterTurbo** branché sur l'agent vidéo ;
3. **ARENA hybride (DEC-0009)** : confidentialité 4 niveaux, Groq + DeepInfra, aiguilleur, banc d'essai ;
4. **Réseaux sociaux actifs (DEC-0010)** : méthode extraite de `charlie947/social-media-skills`, rien copié ;
5. **Coordination des tâches (DEC-0011)** : `grok-bot-0.18-reconstructed` refusé (aucune licence) ; `core/execution/coordination.py` écrit sans emprunt ;
6. **OpenTakeoff — métré de plan PDF (DEC-0012)** : transport MCP stdio, sous-ensemble réel, la limite plafond/mur/rampant corrigée sur indication du propriétaire ;
7. **Crochets d'exécution + disjoncteur (DEC-0013)** : idée extraite de DeepSeek Harness (Cordis refusé), premier consommateur réel — coupe court après des échecs consécutifs réels sur un service tombé ;
8. **Gardien de maintenance (DEC-0014)** : idée extraite de live-swe-agent (aucun code d'agent trouvé, refusé) — DÉCOUVRE et RAPPORTE seulement, jamais MODIFIE (commit/PR autonome explicitement hors périmètre, contraire à la règle non négociable du projet) ; correctif ultérieur pour que `doctor.py` distingue « jamais lancé » de « lancé, rien trouvé » ;
9. `apps/pwa/server/` supprimé (décision du propriétaire) ; correctif `.writing-text` invisible en mode clair sur l'interface ;
10. **Hell-Grind-AIGC-Skill (DEC-0015)** : `tools/video/prompt_audit.py` (audit déterministe de prompt, méthode extraite) + `VideoAnalyzerAgent.planifier_scene()` — premier appelant réel de `wan2gp.generer`, jamais invoqué si l'audit trouve une erreur bloquante ;
11. **GitHub Spec Kit (DEC-0016)** refusé — scaffolding de prompts pour agent de codage humain-supervisé, aucun moteur autonome ; câbler « implement » romprait la garantie PR de CLAUDE.md ;
12. **Agent-Reach (DEC-0017)** refusé — sonde/installateur pour agent de codage (yt-dlp, feedparser, Jina Reader, Exa), rien d'unique ; `DeepResearcherAgent` corrigé à la place : 3 recherches séquentielles → parallèles ;
13. **Consolidation des modèles (DEC-0018)** : inventaire audité, rien à fusionner — léger/profond sont des paliers de coût, pas des doublons ;
14. **Qwen3-VL — vision (DEC-0019)** : `agents/vision/vision_agent.py`, intention `VISION`, `qwen3-vl:4b` servi par Ollama (pas `transformers`), pièces jointes image encodées en mémoire jamais sur disque ; correctif au passage : `pwa_gateway.py` ne transmettait aucune pièce jointe à un agent spécialisé.

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
| **Vision (Qwen3-VL)** | `ollama pull qwen3-vl:4b` pour que `VisionAgent` (DEC-0019) analyse vraiment une image — jamais chargé ni mesuré dans cette session (pas de GPU ici) |
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
