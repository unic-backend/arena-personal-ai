# Audit — 0xranx/OpenContext

**Dépôt étudié** : https://github.com/0xranx/OpenContext
**Commit audité** : `0649e7134346f6f5038a9b29cc5c824ae6a54f3f` (16/06/2026,
tête du dépôt au 10/09/2026).
**Licence** : **MIT** (`LICENSE`, racine, lu directement).
**Méthode** : clone réel, lecture directe de `README.md`, `package.json`,
`src/mcp/server.js` (les dix outils MCP, un par un), `src/core/store/`,
`src/core/search/`. Rien pris sur la seule foi du README.

---

## Ce que le dépôt est réellement

**Une bibliothèque personnelle de notes Markdown, globale (hors dépôt),
avec recherche et un serveur MCP** — pas un système d'invalidation
git-consciente, pas un graphe de dépendances, pas un capteur de
fraîcheur. La mission qui a amené cet audit décrivait un OpenContext
capable de fingerprints, d'invalidation par `git diff`, d'états
STABLE/STALE avec preuve de commit : **rien de tout cela n'existe dans le
dépôt réel**, vérifié en cherchant `git diff`, `invalidat`, `staleness`,
`fingerprint`, `checksum` dans `src/` et `crates/` — zéro résultat. Ce
n'est pas une lacune de l'audit : c'est une lacune du produit.

Ce qu'il fait réellement, bien :

- `oc` CLI (Node.js, `@aicontextlab/cli`) gère une bibliothèque globale de
  dossiers/documents Markdown (`contexts/`), hors de tout dépôt de code.
- Un serveur MCP (`src/mcp/server.js`, `@modelcontextprotocol/sdk`) expose
  **dix outils** : `oc_list_folders`, `oc_list_docs`, `oc_create_doc`,
  `oc_set_doc_desc`, `oc_manifest`, `oc_search` (hybride/vecteur/mot-clé),
  `oc_resolve`, `oc_get_link`, `oc_folder_create`, `oc_index_status`.
- Stockage : SQLite (`better-sqlite3`) pour les métadonnées, **LanceDB**
  (`@lancedb/lancedb`, Apache Arrow) pour les vecteurs — **`openai`** en
  dépendance directe pour les embeddings, **cloud par défaut**.
- `oc init` génère des *skills*/commandes slash pour Cursor, Claude Code et
  Codex — « charge le contexte avant de travailler, persiste ce que tu as
  appris après » — un geste explicite, pas automatique.
- Une app Desktop (Tauri) + une UI Web, avec un éditeur riche
  (Plate/Tiptap) pour éditer les documents à la main.

## Matrice de validation

| Capacité annoncée | Vérifié comment | État |
|---|---|---|
| « Persistent memory » | Fichiers Markdown + SQLite, vraiment persistants | **IMPLEMENTED** |
| Recherche hybride | `oc_search`, modes `hybrid`/`vector`/`keyword` dans `src/core/search/index.js` | **IMPLEMENTED** |
| Liens stables (renommage sans casse) | `oc_resolve`/`oc_get_link`, UUID `stable_id` | **IMPLEMENTED**, idée réutilisable |
| Invalidation Git-consciente | Recherche exhaustive dans `src/`, `crates/` : **aucune ligne** | **ABSENT — n'existe pas** |
| États STABLE/STALE, fingerprints | Idem | **ABSENT — n'existe pas** |
| « Bring your own coding agent » | Skills/slash-commands générés, jamais un agent autonome propre | **IMPLEMENTED, périmètre modeste** |
| Local-first | `openai` en dépendance directe, embeddings cloud par défaut d'après la doc | **CONTREDIT DEC-0002 si utilisé tel quel** |

## Ce qui est réellement réutilisable (idées, jamais code)

1. **Liens stables (`oc_resolve`/`oc_get_link`)** — un identifiant qui
   survit à un renommage/déplacement de fichier. Considéré, **non adopté** :
   pour un dépôt à un seul propriétaire où les chemins de
   `PROJECT_MEMORY/` bougent rarement, la complexité (table d'UUID,
   résolution) dépasse la valeur mesurée ici. `SUGGESTION — NON
   IMPLÉMENTÉE`.
2. **`oc_index_status` : un outil dédié pour dire « l'index existe/n'existe
   pas », avant d'appeler la recherche.** Idée reprise, adaptée : chaque
   `FraicheurFichier` de `core/context/instantane_projet.py` porte son
   propre statut (date déclarée, commits depuis, ou indisponible) —
   distinct par fichier plutôt qu'un statut global, parce qu'ARENA n'a pas
   un seul index mais plusieurs sources (PROJECT_MAP, LOCKED_ZONES,
   DECISIONS).
3. **« Charger le contexte avant de travailler, persister après » comme
   geste EXPLICITE et nommé** (slash-commands `/opencontext-context`,
   `/opencontext-iterate`). Idée reprise, mais rendue **automatique** plutôt
   qu'explicite pour Dioumtoukay : contrairement à un humain dans Claude
   Code qui peut taper une commande, Dioumtoukay ne "pense" pas à charger
   un contexte qu'on ne lui a jamais montré — voir la Décision ci-dessous.
4. **`oc_manifest` : un JSON compact listant les documents d'un dossier.**
   Non repris tel quel : `PROJECT_MEMORY/PROJECT_MAP.md` sert déjà ce rôle,
   à la main, et le dupliquer en JSON généré serait une deuxième source de
   vérité pour la même information.

## Ce qui n'a délibérément pas été repris

- **La bibliothèque globale hors dépôt** — ARENA a un seul propriétaire,
  un dépôt, et `PROJECT_MEMORY/` vit déjà DANS le dépôt (versionné,
  revu par PR comme le reste). Une bibliothèque parallèle hors dépôt serait
  une deuxième source de vérité, interdite par la mission (§3).
- **LanceDB / Milvus / SQLite propre à OpenContext** — ARENA a déjà SQLite
  (`core/memory/`), et pour le vectoriel, Claude Context (Milvus, DEC-0055)
  et LightRAG/GraphRAG (`tools/rag/`). En ajouter un troisième dupliquerait
  ce que la mission interdit explicitement.
- **`openai` comme fournisseur d'embeddings** — DEC-0002 : rien ne part
  chez un fournisseur d'IA. Même garde déjà posée pour Claude Context
  (`_environnement()` écrase `EMBEDDING_PROVIDER` sur `Ollama`).
- **L'app Desktop, l'UI Web, l'éditeur riche** — ARENA n'a pas d'interface
  de gestion de notes ; sa PWA sert la conversation, pas un éditeur de
  documents. Hors périmètre de la mission (« ARENA doit se souvenir »,
  jamais « ARENA doit avoir un éditeur »).

## Décision : le vrai manque n'était pas dans OpenContext, il était mesuré dans ARENA

Avant d'écrire une ligne, l'audit d'ARENA (`core/memory/`, `core/context/`,
`core/connectors/{graphify,gitingest,claude_context,openviking,
txtai_search}.py`, `agents/dioumtoukay/dioumtoukay_agent.py`,
`agents/repo_engineer/repo_engineer_agent.py`, `core/execution/reprise.py`)
a trouvé un écosystème déjà riche :

| Capacité (mission §35) | ARENA existant | OpenContext | Décision |
|---|---|---|---|
| Mémoire personnelle, typée, avec provenance | `core/memory/personnelle.py` (FAIT/PRÉFÉRENCE/INFÉRENCE/CONTEXTE_TEMPORAIRE, expiration) | Documents Markdown plats, pas de typage | **KEEP_ARENA** |
| Mémoire de session courte/longue | `core/memory/memory_manager.py`, partagé par TOUS les agents | — | **KEEP_ARENA** |
| Contexte hiérarchique, budgété en jetons, dédupliqué | `core/connectors/openviking.py` (L0/L1/L2, serveur séparé) | Aucun palier, aucune dédup | **KEEP_ARENA** |
| Recherche sémantique de code, persistante, incrémentale | `core/connectors/claude_context.py` (Merkle tree, Milvus) | `oc_search` (LanceDB, ré-indexé à la main) | **KEEP_ARENA** |
| Graphe structurel du code | `core/connectors/graphify.py` (tree-sitter, hors ligne) | Aucun | **KEEP_ARENA** |
| Repli contenu brut du dépôt | `core/connectors/gitingest.py`, déjà appelé par `RepoEngineerAgent` | Aucun (bibliothèque hors dépôt) | **KEEP_ARENA** |
| Composition multi-source avec provenance | `core/context/recherche_unifiee.py` (code/mémoire/internet, parallèle) | Une seule source (les documents OpenContext) | **KEEP_ARENA, ÉTENDU** — 4ᵉ source `projet` |
| Reprise d'une tâche interrompue | `core/execution/reprise.py` (DEC-0072, journal durable, disque) | Aucun équivalent | **KEEP_ARENA** |
| **Instantané de projet lu AUTOMATIQUEMENT par l'agent de codage avant sa première action** | **ABSENT — mesuré** : `_reperes()` ne lisait jamais `PROJECT_MEMORY/` | Existe, mais **manuel** (slash-command) | **ADAPT_OPENCONTEXT** — l'idée (charger avant de travailler), jamais le code, rendue automatique |
| Fraîcheur/invalidation git-consciente | Absente avant cette mission | **Absente aussi chez OpenContext** | **Ni l'un ni l'autre : conçu ici**, sur la convention de date déjà en place dans `PROJECT_MEMORY/` |
| Liens stables (UUID) | Absent | `oc_resolve`/`oc_get_link` | **NOT_NEEDED** ici — un seul propriétaire, chemins stables |
| UI de gestion de contexte | Absente (pas le rôle d'ARENA) | Desktop + Web | **NOT_NEEDED** |

**La seule capacité réellement manquante était donc étroite et précise** :
rien ne donnait à Dioumtoukay (le seul agent qui MODIFIE le dépôt) ce que
`CLAUDE.md` demande à un humain de lire en premier. `core/context/
instantane_projet.py` comble exactement ce manque, avec deux points
d'entrée :

1. `agents/dioumtoukay/dioumtoukay_agent.py::_reperes()` — automatique,
   avant la première action de toute tâche de codage.
2. `core/context/recherche_unifiee.py` — une 4ᵉ source, `projet`,
   appelable explicitement via `POST /api/contexte/rechercher` pour
   quiconque (pas seulement Dioumtoukay) demande où en est le dépôt.

Rien d'autre n'a été construit : ni base de données, ni service, ni
nouvel agent, ni nouvelle permission — la mission l'interdisait
explicitement (§3), et l'audit a confirmé qu'aucune de ces pièces ne
manquait réellement.

## Ce qui reste `SUGGESTION — NON IMPLÉMENTÉE`

- **Fingerprints par fichier suivi via `git log -- <chemins>` ciblés**,
  plutôt que le compte de commits sur le dépôt entier utilisé ici. Rejeté
  pour cette mission : un mappage fichier→dossiers deviné serait précis en
  apparence et faux en pratique dès qu'une convention de rangement change
  — voir la docstring d'`instantane_projet.py`. Un compte global, plus
  grossier, ne peut pas mentir de la même façon.
- **Liens stables (UUID) pour les entrées de `PROJECT_MEMORY/`** — voir
  ci-dessus, valeur non démontrée pour un seul propriétaire.
- **Un banc de mesure de jetons formel (mission §29)**, avec un vrai
  compteur de jetons contre un modèle réel : aucun modèle n'est joignable
  dans ce bac à sable (`docs/DECISIONS.md`, garde permanente). Une mesure
  de substitution, en caractères, est dans la Vérification ci-dessous —
  jamais présentée comme un compte de jetons exact.
- **Tests dédiés d'injection de prompt (mission §26)** : `instantane_projet.py`
  ne fait que LIRE des fichiers déjà versionnés dans CE dépôt (jamais un
  contenu externe/tiers) — la frontière `core/security/trust.py` ne
  s'applique qu'aux sources externes (e-mail, web, document reçu), pas à
  la documentation du dépôt lui-même. Aucun nouveau vecteur d'injection
  n'est introduit ; un test dédié testerait une garantie qui n'a pas
  changé. Non ajouté pour cette raison, pas par omission.
