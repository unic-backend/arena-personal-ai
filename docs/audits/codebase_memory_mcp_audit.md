# Audit — Codebase-Memory MCP comme capacité d'intelligence structurelle de code

*Audit technique et architectural de l'intégration de Codebase-Memory MCP (DeusData)
dans ARENA / Usman. Évalué le 30/09/2026.*

---

## 1. Provenance et identité

| Élément | Détail |
|---|---|
| Dépôt officiel | https://github.com/DeusData/codebase-memory-mcp |
| Papier de recherche | *Codebase-Memory: Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via MCP* (arXiv:2603.27277) |
| Licence vérifiée | **MIT** (fichier `LICENSE` amont, Copyright (c) 2025-2026 DeusData) |
| Architecture amont | Binaire natif autonome en C, base SQLite intégrée, Tree-Sitter (158+ langages), Hybrid LSP, moteur de requêtes Cypher |
| Protocole d'échange | Model Context Protocol (MCP) en JSON-RPC 2.0 sur stdio (`initialize`, `tools/list`, `tools/call`) |
| Dépendances runtime | **Aucune dépendance externe requise** (pas de Node.js, Python, Docker ni API cloud pour l'indexation de base) |

---

## 2. Comparaison avec les systèmes existants d'ARENA

| Système | Mécanisme | Rôle principal | Limites actuelles | Complémentarité avec Codebase-Memory |
|---|---|---|---|---|
| `gitingest` (`core/connectors/gitingest.py`) | Parseur Python de fichiers | Résumé, arborescence et dump de fichiers | Consomme énormément de jetons sur gros dépôts ; pas de relations d'appels | GitIngest extrait le contenu textuel brut ; Codebase-Memory fournit le graphe structurel |
| `graphify` (`core/connectors/graphify.py`) | Script Python / Tree-sitter | Graphe statique `graph.json` | Lent sur gros projets, pas de requêtes typées, écriture obligatoire sur disque | Codebase-Memory est sous-milliseconde, persistant, avec Cypher et traçage d'appels |
| `claude_context` (`core/connectors/claude_context.py`) | Milvus auto-hébergé + Ollama | Recherche sémantique vectorielle | Exige un serveur Milvus actif et calcul d'embeddings | Complémentaire : Claude Context gère la similarité sémantique, Codebase-Memory gère la structure AST |
| `SWEACITool` / `RepoEngineerTool` | Lecture de répertoires / grep | Inspection de fichiers par les agents de code | Recherche aveugle ligne par ligne sans conscience des dépendances | Codebase-Memory permet un tracé précis des appelants/appelés (`trace_path`) et diff d'impact |

---

## 3. Justification de l'intégration

L'intégration de Codebase-Memory MCP apporte une valeur concrète et mesurable à ARENA :
1. **Économie drastique de jetons** : Jusqu'à 99% de jetons en moins lors de l'exploration de code par les agents (`RepoEngineerAgent`, `SWEAgent`), remplaçant des dizaines de lectures de fichiers complètes par une seule requête de graphe ciblée.
2. **Compréhension relationnelle** : Capacité à remonter et descendre la chaîne d'appels (`trace_path`), trouver qui utilise un symbole et quels modules sont impactés par une modification Git (`detect_changes`).
3. **Persistance locale et rapide** : Base SQLite locale par projet, conservant l'état d'indexation entre sessions sans recalcul complet.
4. **Zéro fuite cloud (Local-First)** : Le binaire tourne 100% en local sur la machine d'Ousmane, sans appel réseau ni fournisseur tiers.

---

## 4. Frontières architecturales et règles d'isolation

- **Séparation stricte des mémoires** : La mémoire de code est strictement cloisonnée au contexte du dépôt/projet (`PROJECT / CODEBASE MEMORY`). Aucune donnée de code ne peut pénétrer la mémoire personnelle de l'utilisateur (`core/memory/personnelle.py`).
- **Frontière de confiance (`core/security/trust.py`)** : Le code source et les sorties du graphe sont traités comme des données non fiables (`TrustLevel.EXTERNAL`). Les balises sont neutralisées et les motifs de prompt-injection sont signalés sans altérer les preuves.
- **Sécurité du système de fichiers** : Exclusion stricte des fichiers et dossiers sensibles (`.env`, `.ssh`, `.gnupg`, `.aws`, clés privées) dès la validation du connecteur, avant tout appel au processus MCP.
- **Cycle de vie éphémère** : Le transport `ClientMcpStdio` est ouvert et fermé dans le cadre de chaque exécution, éliminant tout processus orphelin en arrière-plan.
- **Dégradation gracieuse** : En l'absence du binaire `codebase-memory-mcp`, la sonde retourne `NON_CONFIGURE` et les agents de code basculent automatiquement et silencieusement sur `gitingest`, `repo_tool` ou `swe_aci`.

---

## 5. Synthèse des capacités exposées

Le connecteur `core/connectors/codebase_memory.py` expose 13 capacités normalisées :
1. `indexer` (action `index`, écriture) : Indexation AST complète du dépôt
2. `etat_indexation` (action `read`) : Vérification de l'état d'indexation
3. `lister_projets` (action `read`) : Liste des projets indexés et métriques
4. `supprimer_projet` (action `delete`, écriture, confirmation requise) : Suppression d'un index
5. `architecture` (action `read`) : Synthèse d'architecture (points d'entrée, modules, routes)
6. `rechercher_graphe` (action `read`) : Recherche de symboles typés
7. `tracer_chemin` (action `read`) : Traversée de graphe d'appels (appelants / appelés)
8. `requete_cypher` (action `read`) : Requêtes de motifs Cypher
9. `schema_graphe` (action `read`) : Schéma du métagraphe
10. `extrait_code` (action `read`) : Code source d'un symbole qualifié
11. `plan_fichier` (action `read`) : Déclarations d'un fichier source
12. `impact_modifications` (action `read`) : Analyse d'impact de diff Git
13. `recherche_texte` (action `read`) : Recherche textuelle rapide
