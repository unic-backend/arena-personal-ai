# Audit — Basic Memory (basicmachines-co) comme mémoire d'ARENA

*Audit technique, juridique et architectural demandé le 30/09/2026. La question
posée n'était pas « installer Basic Memory » mais « Basic Memory rend-il la
mémoire d'ARENA substantiellement plus persistante, utile, cherchable et
intelligente, sans créer de mémoire en double, de couplage, de problème de vie
privée ni de problème de licence ? ».*

**Réponse : non. Aucune intégration.** Trois blocages indépendants, chacun
suffisant, et aucun manque réel à combler. Le détail est ci-dessous ; la
décision est `DEC-0203`.

---

## 0. Ce qui a été mesuré, et avec quoi

Toute affirmation de ce document porte sa mesure. Ce qui n'a pas pu être mesuré
est écrit `UNKNOWN — non mesuré`, jamais estimé.

| Mesure | Commande | Date |
|---|---|---|
| Source amont de Basic Memory | `git clone --depth 1 https://github.com/basicmachines-co/basic-memory` → commit `88c3990c`, 29/09/2026 | 30/09/2026 |
| Licence amont | `head LICENSE` + `pyproject.toml` | 30/09/2026 |
| Version Python exigée | `pip install --dry-run basic-memory` sous Python 3.11.2 | 30/09/2026 |
| Licences des dépendances directes | API JSON PyPI, 46 paquets déclarés | 30/09/2026 |
| Capacités réelles d'ARENA | script de mesure (§1.7), `pytest`, `ruff` | 30/09/2026 |
| Suite ARENA de référence | `pytest -q` → 7 913 passés, 52 échecs d'environnement (ni ffmpeg, ni LibreOffice, ni tesseract dans ce bac à sable), 61 ignorés | 30/09/2026 |

---

## 1. AUDIT ARENA — ce qu'elle retient déjà, où, et comment

Le point le plus important de cet audit : **presque rien de ce que Basic Memory
annonce ne manque à ARENA.** Ce n'est pas le même vocabulaire, et c'est la seule
raison pour laquelle on pourrait croire le contraire.

### 1.1 Les cinq mémoires, et qui possède quoi

| Mémoire | Source de vérité | Stockage | Écriture | Lecture |
|---|---|---|---|---|
| **Conversation courante** (session) | `core/memory/memory_manager.py::MemoryManager` | SQLite `data/database/memory.db`, table `short_term_memory` (`session_id`, `role`, `content`, `timestamp`) | `add_chat_message()` à chaque tour | `get_recent_history(limit)`, plafonné à `MAX_RECENT_HISTORY=200` |
| **Faits clés** (clé/valeur catégorisés) | même module, table `long_term_memory` | SQLite, index unique `(category, key)` | `set_fact()` en `UPSERT` | `get_fact(key, category)` — une clé ambiguë sur deux catégories **lève** `AmbiguousMemoryFactError` au lieu de deviner |
| **Mémoire personnelle** (le cœur) | `core/memory/personnelle.py::MemoirePersonnelle` (1 209 lignes) | SQLite, `PRAGMA journal_mode=WAL` | `retenir()` — refuse sans `source` | `souvenirs()`, `recuperer()`, `recuperer_semantique()` |
| **Mémoire documentaire** (connaissance durable) | `core/knowledge/vault.py::KnowledgeVault` (780 lignes) | Markdown sur disque sous `data/knowledge_vault/` (hors Git), trois couches `raw/` → `wiki/` → `output/` | `ingest()` — source brute immuable + note Markdown sourcée | `search()` BM25, `hybrid_search()` BM25+dense+RRF, `find_text()`, `read_page()`, `list_pages()`, `graph()` |
| **Mémoire opérationnelle du dépôt** | `PROJECT_MEMORY/*.md` | Markdown versionné | à la main, par session | lue en premier par chaque session (`CLAUDE.md`) |

Il n'y a **pas** de sixième mémoire à inventer : chacune a déjà un propriétaire
unique, et `core/knowledge/vault.py` dit explicitement en tête de fichier qu'il
« ne remplace ni `core/memory/` ni `PROJECT_MEMORY/` ».

### 1.2 Le modèle de souvenir — provenance, cycle de vie, validité

`Souvenir` (gelé, `@dataclass(frozen=True)`) porte déjà tout ce que la mission
§14 demande sous le nom « provenance » :

- `type` — six valeurs : `EPISODIC`, `SEMANTIC`, `PROCEDURAL`, `TASK`,
  `DECISION`, `MISTAKE` ;
- `nature` — quatre valeurs : `FACT`, `PREFERENCE`, `INFERENCE`,
  `TEMPORARY_CONTEXT`. **Une `INFERENCE` ne devient `FACT` que par
  `confirmer()`, qui exige une source nouvelle** ;
- `etat` — `ACTIVE` / `REJECTED` / `ARCHIVED`, orthogonal à la nature ;
- `source` (obligatoire — un dépôt sans source est refusé) et `sources`
  (les voix **distinctes** qui affirment la même chose, ce qui distingue
  « corroboré » de « insiste ») ;
- `occurrences`, `cree_le`, `vu_le`, `expire_le`, `valide_depuis`
  (« vrai à partir de » — distinct de « écrit le ») ;
- `importance` déclarée entre 0 et 1, par défaut 0,5 — *le milieu, jamais le
  haut* ;
- `projet` — la frontière d'isolation ;
- `sensible` — chiffrement au repos.

Basic Memory offre `title`, `type`, `tags`, `permalink`, `entity_metadata` et
des observations catégorisées. **Il n'a aucun équivalent de `nature`, `etat`,
`valide_depuis`, `sources` ni `sensible`.** Sur la qualité de connaissance
(mission §14), ARENA est en avance, pas en retard.

### 1.3 Récupération

Trois moteurs, tous locaux, tous déjà branchés :

1. **Lexical** — `core/memory/recuperation.py` (423 lignes) : quatre signaux
   (correspondance, importance, récence, fenêtre temporelle évoquée), budget
   en caractères **dur** (un souvenir qui déborderait n'est pas tronqué, il
   n'est pas pris), fusion bornée de deux fenêtres de lecture.
2. **Sémantique** — `core/memory/semantique.py` (355 lignes) : cinquième signal
   par embeddings **locaux** (Ollama, `bge-m3`). Sans serveur, le résultat porte
   `mode="LEXICAL"` et la raison mesurée ; **aucun classement sémantique n'est
   jamais simulé**. Un vecteur de mauvaise dimension est refusé, pas tronqué.
3. **Documentaire** — `core/knowledge/retrieval.py` (233 lignes) : Okapi BM25
   écrit à la main (pas de dépendance), Reciprocal Rank Fusion, fournisseur
   dense injectable, métriques Recall@k / NDCG@k. Repli BM25 explicite et
   étiqueté.

Plus `core/context/recherche_unifiee.py` (284 lignes) qui assemble le contexte
de plusieurs sources, et `core/context/fil_pour_agents.py` qui le donne aux
agents.

### 1.4 MCP — client **et** serveur, déjà là

- **Client HTTP** : `core/mcp/transport.py` (213 lignes), streamable-HTTP,
  poignée de main + `tools/list` + `tools/call`, distingue l'échec de transport
  (`ok=False`) de l'échec applicatif (`isError`) — mesuré sur deux serveurs
  réels.
- **Client stdio** : `core/mcp/stdio_transport.py` (297 lignes), utilisé par les
  connecteurs OpenTakeoff et Codebase-Memory.
- **Serveur MCP de mémoire** : `core/mcp/memory_server.py` (181 lignes), six
  outils — `search_memory`, `create_memory`, `list_memory`, `approve_memory`,
  `reject_memory`, `delete_memory`. Gouvernance non contournable : un client MCP
  externe écrit toujours `Nature.INFERENCE`, jamais un `FAIT`.

**Il existe donc déjà une architecture MCP d'ARENA.** La mission §7 interdit
d'en créer une seconde ; il n'y avait rien à créer.

### 1.5 Vie privée, secrets, suppression

- **Chiffrement au repos** : `core/memory/chiffrement.py` (308 lignes),
  AES-256-GCM, clé dérivée d'une phrase de passe jamais dans le code. Sans
  coffre configuré, `retenir(..., sensible=True)` **refuse** plutôt que d'écrire
  en clair sous couvert de sécurité.
- **Refus d'écrire un secret** : `personnelle.py::_motif_secret_dans()` réutilise
  `scripts/scanner_secrets.py::MOTIFS_NOMMES` — **la même liste** qui protège un
  commit, jamais une seconde liste inventée.
- **Suppression réelle** : `MemoirePersonnelle.supprimer()`, `DELETE
  /api/memory/{id}`, `delete_memory` en MCP. Aucun index séparé à purger.
- **Contenu non fiable** : `core/security/trust.py::wrap(..., TrustLevel)` —
  toute sortie de vault ou d'outil est enveloppée comme DONNÉE, jamais comme
  instruction.

Basic Memory n'a **aucun** de ces quatre mécanismes (§2.7).

### 1.6 Conflits, consolidation, cycle de vie

- `core/memory/contradiction.py` (248 lignes) : détection et signalement des
  souvenirs qui se contredisent.
- `core/memory/consolidation.py` (212 lignes) : regroupe les doublons **sans
  rien supprimer**, ne traverse jamais une nature / un type / un projet / une
  source, importance du groupe = maximum, jamais une moyenne calculée.
- `core/memory/etat.py`, `core/memory/recuperation.py` : le contexte temporaire
  expire (`DUREE_CONTEXTE_HEURES = 12` par défaut).
- Décision de mémoriser : `retenir()` est appelé explicitement, avec une
  `source` obligatoire. **ARENA n'enregistre pas chaque conversation
  automatiquement** — exactement ce que la mission §8 demande.

### 1.7 Vérification par la mesure, pas par la lecture

```
$ python /tmp/mesure_arena.py            # 30/09/2026
INGEST: {'status': 'INGESTED', 'source': '…/vault/raw/tarif-de-pose-9dfaf81a5205.md',
         'wiki_page': '…/vault/wiki/sources/tarif-de-pose-9dfaf81a5205.md',
         'sha256': '9dfaf81a5205…', 'passages': 1, 'characters': 87}
SEARCH bm25: [('sources/tarif-de-pose-9dfaf81a5205.md', 1.394, 'BM25')]
GRAPH: {'nodes': 3, 'edges': 1, 'broken_links': 1}
HYBRID (sans Ollama): [('sources/tarif-de-pose-9dfaf81a5205.md', 'BM25')]
LINT: {'broken_links': [{'source': '…', 'target': 'Chantier Medina'}],
       'orphans': [], 'unprocessed_raw': [], 'missing_provenance': [],
       'duplicate_pages': [], 'healthy': False}
ISOLATION Medina     -> ['18 parois posees a Medina.']
ISOLATION Fast Group -> ['18 parois posees pour Fast Group.']
PROJETS: ['Fast Group', 'Medina']
```

Lu ligne par ligne : ARENA **ingère du Markdown**, **construit un graphe de
wikiliens** (3 nœuds, 1 arête, 1 lien cassé détecté), **cherche en BM25**,
**bascule en repli étiqueté quand les embeddings sont absents** au lieu de
simuler, **lint** les liens cassés / orphelins / provenance manquante, et
**isole les projets** (une question sur Medina ne rend rien de Fast Group).

C'est, mot pour mot, la liste des arguments de vente de Basic Memory.

### 1.8 Ce qui manque vraiment à ARENA

Après relecture complète : **rien que Basic Memory apporterait.** Les deux
manques réels mesurés pendant cet audit sont ailleurs et ne le concernent pas :

1. Les embeddings (`bge-m3`) exigent Ollama, donc la machine du propriétaire.
   Hors de sa machine, la récupération reste lexicale et le dit.
   `UNKNOWN — non mesuré` sur sa RTX A2000.
2. Le Knowledge Vault n'est pas exposé par le serveur MCP (seule la mémoire
   personnelle l'est). C'est un choix, pas un manque : les agents y accèdent
   déjà par `apps/backend/services/tools/builtin.py`
   (`KnowledgeSearch`, `KnowledgeExplorer`) et `ResearcherAgent`. Aucun besoin
   exprimé par le propriétaire. `SUGGESTION — NON IMPLÉMENTÉE`.

---

## 2. AUDIT BASIC MEMORY — le dépôt réel, pas sa page d'accueil

Cloné et lu le 30/09/2026, commit `88c3990c`, `__version__ = "0.23.2"`,
`CHANGELOG` à `v0.24.0 (2026-09-29)`.

### 2.1 Identité et état

| Élément | Constat mesuré |
|---|---|
| Dépôt | https://github.com/basicmachines-co/basic-memory |
| Licence | **AGPL-3.0-or-later** (`LICENSE` = texte AGPLv3 ; `pyproject.toml` : `license = { text = "AGPL-3.0-or-later" }`) |
| Taille | **128 338 lignes de Python** sous `src/` |
| Tests amont | 567 fichiers `test_*.py` (`tests/` + `test-int/`) |
| Maintenance | **Active.** Dernier commit 29/09/2026, `CHANGELOG` daté du même jour |
| Python exigé | `requires-python = ">=3.12"` |
| Modèle économique | Offre cloud payante (15 $/mois), bandeau promotionnel dans le README **et dans la CLI** |

### 2.2 Architecture réelle

Une seule base de code sert quatre entrées : une **CLI** (`typer`, commandes
`bm`/`basic-memory`), une **API FastAPI** (`api/`, `api/v2/`), un **serveur MCP**
(`fastmcp`), et un **indexeur/watcher** (`index/`, `indexing/` — 40 modules
rien que pour l'indexation). Le serveur MCP ne parle pas directement à la base :
il monte l'application FastAPI **en transport ASGI in-process**
(`mcp/async_client.py::_build_asgi_client`, `ASGITransport(app=app)`) ou, en
mode cloud, la remplace par un client HTTP distant. Les revendications sont donc
vérifiées ainsi :

| Revendication amont | Vérifié dans le code ? |
|---|---|
| Local-first | **Partiellement.** Le stockage l'est ; la CLI a des chemins réseau par défaut (§2.6) et un mode cloud de premier ordre (`BASIC_MEMORY_FORCE_CLOUD`, `has_cloud_credentials`) |
| Markdown comme source de vérité | **Oui.** `NOTE-FORMAT.md` : frontmatter YAML, `- [catégorie] observation #tag (contexte)`, `- relation [[Cible]]`. Le fichier fait foi, la base est un index |
| MCP-natif | **Oui.** `fastmcp==4.0.3`, ~30 outils exposés dont six outils POSIX (`cat`, `grep`, `ls`, `find`, `tail`, `man`) **activés par défaut depuis #1476** |
| Graphe de connaissances | **Oui.** Entités / observations / relations, résolution de liens différée (`indexing/forward_reference_resolution.py`) |
| Recherche sémantique | **Oui.** `sqlite-vec` en SQLite, `pgvector`/Milvus en Postgres ; `fastembed` par défaut ; reranking cross-encoder optionnel |
| SQLite | **Oui, mais pas seulement.** `database_backend` accepte `sqlite` ou `postgres` (`asyncpg`, `psycopg`), plus un cache Redis optionnel |

### 2.3 Outils MCP exposés

`src/basic_memory/mcp/tools/__init__.py` : `write_note`, `read_note`,
`view_note`, `edit_note`, `move_note`, `delete_note`, `read_content`,
`list_directory`, `search_notes`, `build_context`, `recent_activity`,
`list_memory_projects`, `create_memory_project`, `delete_project`,
`list_workspaces`, `schema_validate`, `schema_infer`, `schema_diff`,
`basic_memory_diagnostics`, `search`, `fetch`, plus `cat`, `find`, `grep`,
`ls`, `man`, `tail`.

**Trois opérations destructives (`delete_note`, `move_note`, `delete_project`)
sont exposées par défaut, sans autorisation explicite.** La mission §7 demande
l'inverse. ARENA aurait dû les filtrer côté adaptateur — faisable, mais c'est un
travail de confinement pour un composant qu'on n'a par ailleurs aucune raison
d'ajouter.

### 2.4 Isolation des projets — une faille de conception pour ARENA

Les projets existent (`list_memory_projects`, paramètre `project` sur presque
tous les outils). Mais `BasicMemoryConfig.default_project` est décrit ainsi dans
`config_models.py` :

> *« Name of the default project to use. When set, acts as fallback when no
> project parameter is specified. »*

**Un outil appelé sans `project` retombe silencieusement sur le projet par
défaut.** Pour ARENA, dont la mission §9 exige qu'une requête d'un projet ne
puisse jamais ramener celle d'un autre, c'est un repli qui va exactement dans la
mauvaise direction : l'oubli d'un paramètre ne produit pas une erreur, il produit
une réponse venue d'ailleurs. ARENA, elle, filtre en SQL
(`personnelle.py::souvenirs`, `AND projet = ?`) et n'a pas de projet par défaut.

### 2.5 Dépendances et exigences d'exécution

46 dépendances directes déclarées, dont `fastapi[standard]`, `sqlalchemy`,
`alembic`, `asyncpg`, `psycopg`, `fastembed` (donc `onnxruntime`), `sqlite-vec`,
`openai`, `litellm`, `logfire`, `pillow`, `watchfiles`, `uvloop`, `pyright`
(un vérificateur de types **en dépendance d'exécution**), `pytest-aio` et
`pytest-asyncio` (des outils de test **en dépendance d'exécution**). Extras :
`pymilvus`, `redis`, `pdf-inspector`, `markitdown`.

`requirements.txt` d'ARENA a déjà cassé la CI sur un conflit de versions — c'est
écrit dans l'en-tête de `core/mcp/transport.py`, qui existe précisément parce
qu'on a refusé d'ajouter le SDK `mcp` à l'époque. Ajouter 46 dépendances de plus
va dans le sens opposé à toute l'histoire du dépôt.

### 2.6 Sorties réseau par défaut — mesurées, et nuancées

Trois chemins d'égression existent par défaut dans la CLI :

| Chemin | Destination | Déclenché quand ? |
|---|---|---|
| Analytique Umami | `https://api-gateway.umami.dev` (identifiant de site en dur dans `cli/analytics.py`) | Bandeau promotionnel affiché, ou connexion cloud |
| Vérification de version | `https://pypi.org/pypi/basic-memory/json`, puis **mise à jour automatique** via `uv`/`brew` (`cli/auto_update.py`) | Après chaque commande interactive |
| Téléchargement du modèle | HuggingFace, via `fastembed` | Premier usage de la recherche sémantique |
| Logfire | Désactivé par défaut (`logfire_enabled=False`, `logfire_send_to_logfire=False`) | Jamais sans configuration |

**Nuance honnête, mesurée dans le code** : `maybe_show_cloud_promo` et
`maybe_run_periodic_auto_update` sortent tous deux immédiatement si
`invoked_subcommand in {None, "mcp"}` ou si la session n'est pas interactive
(`sys.stdin.isatty() and sys.stdout.isatty()`). **Le chemin MCP stdio, celui
qu'ARENA utiliserait, ne déclenche donc ni analytique ni auto-mise-à-jour.**
Ce n'est pas un blocage ; c'est un comportement par défaut qu'il faudrait
surveiller à chaque montée de version, pour un composant dont on n'a pas besoin.

Le téléchargement de modèle, lui, reste : `fastembed` va chercher les poids
en ligne au premier usage. La revendication « local-first » est vraie pour les
données, pas pour l'amorçage.

### 2.7 Modèle de sécurité — ce qu'il n'a pas

Recherché explicitement dans le source amont, et **absent** :

- aucun chiffrement au repos des notes ;
- aucun refus d'écrire un contenu qui ressemble à un secret ;
- aucune notion de niveau de confiance du contenu récupéré (ARENA :
  `core/security/trust.py`) ;
- aucune séparation fait / inférence, donc aucune barrière empêchant un agent de
  transformer une supposition en vérité de la base.

Pour un composant destiné à recevoir du contexte de chantier, des tarifs, des
noms de clients et des extraits de dépôt, ce sont quatre régressions par rapport
à ce qu'ARENA garantit aujourd'hui.

### 2.8 Modèle d'embedding par défaut

`semantic_embedding_model = "bge-small-en-v1.5"` — un modèle **anglais**.
Le corpus du propriétaire est en français (et son vocabulaire métier l'est
entièrement : cloisons, BA13, plafonds, plaquiste). ARENA utilise déjà `bge-m3`,
multilingue, en local. Le modèle est configurable chez Basic Memory ; le défaut
est néanmoins révélateur de la cible du projet.

`UNKNOWN — non mesuré` : aucune comparaison de qualité de récupération
français `bge-m3` (ARENA) contre `bge-small-en-v1.5` (Basic Memory) n'a été
faite. Elle exigerait un jeu labellisé et la machine du propriétaire.

---

## 3. LES TROIS BLOCAGES

Chacun suffit à lui seul. Ils sont indépendants : lever l'un ne lève pas les
autres.

### Blocage 1 — Licence : AGPL-3.0-or-later contre « tous droits réservés »

`LICENSE` d'ARENA : *« Usman is proprietary software… No licence, express or
implied, is granted to any person. »* Le dépôt est **public** depuis le
06/09/2026.

- **Copier du code Basic Memory dans ce dépôt est exclu.** Ce serait une œuvre
  dérivée sous AGPL-3.0, publiée sur un dépôt public sous une licence qui dit
  l'inverse. Même règle que DEC-0200 (Edit-Banana, AGPL) et DEC-0202
  (Netronome, GPL-2.0), déjà tenues par
  `tests/test_moteurs_externes_restent_dehors.py`.
- **La clôture de dépendances est elle aussi copyleft.** Sur les 46 dépendances
  directes déclarées, mesurées via l'API PyPI le 30/09/2026 :
  **`unidecode` est GPL-2.0-or-later** et **`psycopg` est LGPL-3.0-only**. Le
  reste est permissif (MIT, Apache-2.0, BSD-3-Clause, MIT-CMU). Un environnement
  Python d'ARENA qui embarquerait basic-memory embarquerait donc aussi du
  GPL-2.0+ et du LGPL-3.0.
- **Le processus séparé reste la seule forme envisageable**, comme pour
  Netronome (agrégation). Mais l'AGPL §13 est la clause la plus agressive du
  paysage : elle vise l'interaction **à travers un réseau** avec une version
  modifiée. ARENA *est* déployée en service réseau (FastAPI, Railway). La
  frontière « programme séparé, non modifié, invoqué en stdio localement » est
  défendable, elle n'est pas certaine, et **ce n'est pas à un agent
  d'implémentation de trancher une question de droit à la place du
  propriétaire**. La mission §11 dit : *« Do not guess about licensing. If
  licensing creates an unresolved blocker, do not integrate it. Report the
  blocker instead. »* C'est ce qui est fait ici.

### Blocage 2 — Version de Python : mesuré, sans appel

```
$ python3 --version
Python 3.11.2
$ pip install --dry-run basic-memory
ERROR: Ignored the following versions that require a different python version:
  … 0.23.2 Requires-Python >=3.12 … (toutes les versions publiées)
ERROR: Could not find a version that satisfies the requirement basic-memory
ERROR: No matching distribution found for basic-memory
```

ARENA tourne en **Python 3.11** : `.github/workflows/ci.yml` pose
`python-version: "3.11"`, avec le commentaire « Même version que
`apps/backend/Dockerfile` », et `pyproject.toml` fixe
`target-version = "py311"`. **Aucune version de basic-memory, depuis la 0.0.0,
n'est installable dans l'environnement d'ARENA.** Une dépendance Python est
donc impossible aujourd'hui, sans exception ni contournement.

Un sous-processus MCP avec son propre interpréteur 3.12+ contournerait ce point
— mais il faudrait alors installer Python 3.12 sur la machine du propriétaire
pour un composant que le blocage 3 rend inutile.

### Blocage 3 — Ce serait une seconde mémoire, pas une meilleure mémoire

C'est le blocage qui compte, et le seul qui resterait si les deux autres
tombaient.

| Capacité annoncée par Basic Memory | Équivalent ARENA, déjà écrit et testé |
|---|---|
| Notes Markdown, source de vérité, wikiliens Obsidian | `core/knowledge/vault.py` — `raw/`/`wiki/`/`output/`, `[[liens]]`, frontmatter sourcé, `lint()` |
| Graphe de connaissances | `KnowledgeVault.graph()` (mesuré §1.7 : nœuds, arêtes, liens cassés) |
| Recherche sémantique / hybride / reranking | `core/knowledge/retrieval.py` (BM25 + RRF + dense injectable) et `core/memory/semantique.py` (5 signaux) |
| Index SQLite | `core/memory/personnelle.py` (WAL), `core/memory/memory_manager.py` |
| Outils MCP mémoire | `core/mcp/memory_server.py` — 6 outils, gouvernance FAIT/INFERENCE non contournable |
| Projets / espaces de travail | champ `projet` filtré en SQL partout, `core/context/projet.py`, `core/context/instantane_projet.py` |
| `recent_activity` | `MemoirePersonnelle.souvenirs()`, `core/context/instantane_projet.py` |
| `build_context` | `core/context/recherche_unifiee.py`, `core/context/fil_pour_agents.py` |
| CLI | `scripts/knowledge_vault.py`, `scripts/evaluer_knowledge_vault.py` |
| Provenance | `source`, `sources`, `cree_le`, `vu_le`, `occurrences`, `nature`, `etat`, `importance`, `valide_depuis` |
| Détection de conflit | `core/memory/contradiction.py` |
| Suppression | `supprimer()`, `DELETE /api/memory/{id}`, `delete_memory` (MCP) |
| — *sans équivalent amont* — | **chiffrement au repos** (`core/memory/chiffrement.py`) |
| — *sans équivalent amont* — | **refus d'écrire un secret** (motifs partagés avec le scanner de commit) |
| — *sans équivalent amont* — | **frontière de confiance** (`core/security/trust.py`) |
| — *sans équivalent amont* — | **FAIT vs INFERENCE**, promotion seulement par `confirmer()` |

L'intégrer produirait deux corpus Markdown, deux index SQLite, deux graphes,
deux moteurs de recherche sémantique et deux notions de « projet », sans qu'un
seul besoin soit couvert par l'un et pas par l'autre. **C'est exactement ce que
la mission §3 interdit**, et ce que le dépôt refuse déjà depuis DEC-0008.

---

## 4. Les quatre options, et pourquoi trois tombent

| Option | Verdict | Raison |
|---|---|---|
| **A — Ne pas intégrer** | **RETENUE** | Blocages 1, 2 et 3. |
| **B — Backend mémoire MCP optionnel** | Rejetée | Duplique `MemoirePersonnelle` trait pour trait, en perdant `nature`/`etat`/chiffrement/refus de secret. Une mémoire optionnelle qui contient la moitié des souvenirs est pire qu'aucune. |
| **C — Couche de connaissance spécialisée** | Rejetée | C'est le rôle **déjà rempli** par `core/knowledge/vault.py` (DEC-0130), Markdown compris. Deux vaults Markdown côte à côte : la question n'est plus « où est-ce écrit » mais « dans lequel des deux ». |
| **D — Usage développement / agent de code seulement** | Rejetée **en tant que changement du dépôt** | Le besoin est déjà couvert par `PROJECT_MEMORY/` (contexte d'ingénierie persistant, versionné, lu en premier à chaque session) et par DEC-0201 (Codebase-Memory MCP, MIT, pour la structure du code). Si le propriétaire veut un jour l'essayer comme outil personnel sur **sa** machine, hors du dépôt, cela ne demande **aucun changement ici** — et cela reste soumis au blocage 2 (installer Python 3.12). |

Le plugin Claude Code de Basic Memory (`plugins/`, `skills/`) n'a pas été
examiné au-delà de son existence : la mission §16 demande de ne pas l'importer
sans besoin prouvé, et aucun besoin n'est prouvé.

---

## 5. Ce que la décision engage — et ce qu'elle ne dit pas

**Ce qu'elle dit** : aucune dépendance, aucun sous-processus, aucun connecteur,
aucune ligne de Basic Memory dans ARENA. Aucune attribution n'est due, puisque
rien n'est utilisé : `THIRD_PARTY_NOTICES.md` et `NOTICE.md` ne sont donc **pas**
modifiés — y écrire une entrée laisserait croire à un usage.

**Ce qu'elle ne dit pas** :

- Elle ne dit pas que Basic Memory est un mauvais projet. Il est actif, largement
  testé (567 fichiers de test), et cohérent pour sa cible : un utilisateur qui
  n'a pas déjà construit sa mémoire.
- Elle ne dit pas qu'ARENA est plus rapide, plus précise ou moins gourmande.
  **Aucune comparaison de performance n'a été faite** : ni latence de recherche,
  ni coût d'indexation, ni usage disque, ni comportement à grande base, ni accès
  concurrent, ni reconstruction d'index. `UNKNOWN — non mesuré`, et ce le
  restera tant que les deux systèmes ne tourneront pas sur le même corpus, sur
  la machine du propriétaire.
- Elle ne dit pas « jamais ». Elle se rouvre le jour où **les trois** blocages
  tombent : un avis juridique sur l'AGPL §13 pour un service réseau, Python 3.12
  sur la machine et dans la CI, **et** une capacité nommée que le Knowledge
  Vault ne sait pas rendre.

---

## 6. Régression — ce qui a été exécuté

Aucun code d'ARENA n'est modifié par cet audit. Les mesures :

```
$ ruff check .
All checks passed!

$ pytest -q
52 failed, 7913 passed, 61 skipped, 61 deselected in 186.38s
```

Les 52 échecs sont **antérieurs à cet audit et propres au bac à sable** : ni
`ffmpeg`, ni `soffice` (LibreOffice), ni `tesseract` n'y sont installés, alors
que la CI les installe (`.github/workflows/ci.yml`). Ils portent tous sur PDF,
conversion de documents et découpe vidéo. Vérifié :

```
$ which ffmpeg soffice tesseract
(aucune sortie)
```

Le périmètre réellement concerné par la décision passe intégralement :

```
$ pytest -q tests/core/test_memoire_personnelle.py tests/core/test_knowledge_vault.py \
           tests/core/test_mcp_memory_server.py tests/core/test_recuperation_memoire.py \
           tests/core/test_memoire_gouvernance.py tests/test_moteurs_externes_restent_dehors.py
227 passed in 13.62s
```

Le test qui **tient** cette décision est
`tests/test_basic_memory_reste_dehors.py` : il mesure qu'aucune dépendance ni
import n'est apparu, et que les capacités sur lesquelles le refus repose
existent encore. Le jour où l'une disparaît, le test échoue et la décision doit
être rouverte au lieu de rester vraie par inertie.
