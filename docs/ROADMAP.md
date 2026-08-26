# ROADMAP DU PROJET — Usman

> **Règle de tenue** (posée le 26/08/2026) : une case n'est cochée qu'après une
> vérification exécutée. Une case cochée à tort est pire qu'une case vide —
> personne ne revient sur un point déclaré clos.
> Le détail des vérifications est dans `documents/USMAN_ENGINEERING_WORKLOG.md`.

## PHASES 0 À 5 — FONDATIONS [TERMINÉ]
- [x] Diagnostic matériel (RTX A2000 12 Go / Ollama)
- [x] Arborescence unifiée et système de permissions
- [x] Moteur IA local Ollama — *le tag `qwen3.5:9b` reste à confirmer, voir Phase 8*
- [x] Backend FastAPI et tableau de bord Web
- [x] Mémoire persistante SQLite (`memory.db`)
- [x] CoderAgent autonome avec auto-correction
- [x] DeepResearcherAgent (recherche multi-sources)
- [x] TrendAnalyzerAgent (Sénégal, Afrique, Monde)
- [x] Studio Vidéo 1-Click (FFmpeg + Whisper + 9:16 + SRT)
- [x] ClipSelectorAgent (détection du meilleur extrait)

## PHASE 6 — PLATEFORME ET AGENTS AVANCÉS [TERMINÉ]
- [x] Passerelle compatible OpenAI (`/v1`)
- [x] LibreChat (:3080) et Open WebUI (:3000)
- [x] ReasoningEngine (Plan & Solve + SymPy)
- [x] Browser-Use + Playwright (navigation web)
- [x] SWEAgent et RepoEngineerAgent (analyse, lecture seule)

## PHASE 7 — SÉCURITÉ ET FIABILITÉ [PARTIEL — v1.7.0]

Trois des six livrables de cette phase avaient été cochés sans vérification.
L'audit du 26/08/2026 les a repris un par un. État réel :

- [x] Clé API obligatoire sur la passerelle `/v1`
- [x] Validation des chemins de fichiers (`validate_media_path`)
- [x] LightRAG et GraphRAG branchés — *aucun document indexé à ce jour*
- [ ] ~~Bac à sable Docker actif~~ → **reformulé**, voir Phase 7 bis.
      Le bac à sable n'était « actif » que si Docker tournait ; sinon le code
      s'exécutait sur la machine sans isolation.
- [ ] ~~Secrets déplacés vers `.env` et renouvelés~~ → **partiellement faux**.
      Le fichier est propre depuis le 26/08, mais **la clé n'a pas été renouvelée
      et reste lisible dans l'historique Git**. Voir Phase 7 bis, point 1.
- [x] ~~Dépôt Git assaini, dépendances complètes, tests fiables~~ → **refait**
      pour de bon en Phase 7 bis : dépendances séparées, 148 tests exécutables,
      historique Git réel. « Assaini » reste faux tant que le secret y figure.

## PHASE 7 bis — CORRECTION [EN COURS]

Ouverte le 26/08/2026 après quatre rapports d'audit. Chaque ligne cochée
correspond à un commit et à une vérification consignée dans le worklog.

- [x] Clé API sortie du fichier `librechat.yaml` (variable d'environnement)
- [x] Authentification sur les quatre routes `/api/*`
- [x] CORS restreint aux interfaces locales, `*` supprimé
- [x] Bac à sable : **refuser** l'exécution au lieu de la dégrader
- [x] `EXECUTE_COMMANDS: false` par défaut
- [x] `requirements.txt` portable (le build Docker Linux était impossible)
- [x] Suite de tests exécutable hors ligne — 148 tests, 17 marqués `integration`
- [x] `ruff` configuré, dépôt à zéro erreur
- [x] LICENSE, CI GitHub Actions, `.dockerignore`
- [x] Classification d'intention par le modèle, repli mots-clés annoncé
- [x] BOM UTF-8 retiré (37 fichiers)
- [x] `/api/upload` : filtre de type, plafond de taille, écriture par blocs
- [x] Documentation alignée sur le code (ce fichier compris)
- [ ] **Rotation de la clé et purge de l'historique Git** — bloqué, décision du
      propriétaire requise. C'est le dernier point critique ouvert.
- [ ] Scan de secrets en CI (`gitleaks`)
- [ ] Limitation de débit sur les routes qui appellent le modèle
- [ ] Journalisation des échecs d'authentification

## PHASE 8 — À VENIR

Rien ici n'est commencé.

**Matériel et performance** — *aucune mesure n'existe encore ; les chiffres
ci-dessous sont des estimations sur papier, pas des relevés.*
- [ ] Confirmer que le tag `qwen3.5:9b` existe (`ollama list`)
- [ ] Mesurer la VRAM réellement occupée par chaque modèle
- [ ] Arbitrer le budget VRAM (deux modèles estimés à ~15,6 Go pour une carte de 12 Go)

**Capacités**
- [ ] Pipeline d'information fraîche : recherche → lecture → synthèse → sources citées
- [ ] Retirer les faits datés écrits en dur dans le prompt système
- [ ] Indexation de documents dans GraphRAG / LightRAG
- [ ] Mémoire sémantique et mémoire utilisateur séparées
- [ ] Progression visible pendant les opérations longues

**Dette technique**
- [ ] Découper `apps/backend/main.py` (459 lignes, 8 routes)
- [ ] Interface web fonctionnelle hors ligne (Tailwind en local)
- [ ] Accès SQLite non bloquant depuis les routes `async`

**Extension**
- [ ] Publication réelle sur les réseaux (actuellement en simulation, `DEC-0003`)
