# ROADMAP DU PROJET - ARENA

## PHASES 0 À 5 — FONDATIONS [TERMINÉ]
- [x] Diagnostic matériel (RTX A2000 12 Go / Ollama / Python 3.14)
- [x] Arborescence unifiée et système de permissions
- [x] Moteur IA local (Qwen 3.5:9b + Qwen 2.5 Coder:14b)
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

## PHASE 7 — SÉCURITÉ ET FIABILITÉ [TERMINÉ - v1.7.0]
- [x] Clé API obligatoire sur la passerelle `/v1`
- [x] Validation des chemins de fichiers
- [x] Bac à sable Docker actif (`arena-sandbox`)
- [x] Secrets déplacés vers `.env` et renouvelés
- [x] LightRAG et GraphRAG réparés
- [x] Dépôt Git assaini, dépendances complètes, tests fiables

## PHASE 8 — À VENIR
- [ ] Indexation de documents dans GraphRAG
- [ ] Arbitrage du budget VRAM (15,6 Go de modèles pour 12 Go de carte)
- [ ] Interface web fonctionnelle hors ligne (Tailwind en local)
- [ ] Publication réelle sur les réseaux (actuellement en simulation)
