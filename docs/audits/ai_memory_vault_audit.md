# Audit — ai-encryption-tool/ai (« AI Memory Vault »)

## Provenance

**Dépôt étudié** : https://github.com/ai-encryption-tool/ai
**Commit audité** : `5e6d218c1b21a7dd71e94bb6d090c7f153b6f910` (20/08/2026, tête du dépôt
au 11/09/2026).
**Licence** : **MIT** (`LICENSE`, racine, lu directement).
**Méthode** : clone réel (`git clone --depth 1`), lecture directe de
`backend/app/{main,models,database,vector_store,importers,suggestions,ask,auth,config}.py`,
`mcp_server/server.py`, `frontend/src/cryptoVault.js`, `backend/tests/test_api.py`.
Rien pris sur la seule foi du README.

## Ce que le dépôt fait réellement (vérifié dans le code, pas dans le README seul)

| Domaine | Fichier(s) | Constat |
|---|---|---|
| Backend local | `backend/app/main.py` | FastAPI, SQLite (`database.py`), une seule clé d'API globale (`config.py`, défaut `dev-local-api-key-change-me`) |
| Modèle de mémoire | `backend/app/models.py` | `Memory` : `type`, `content`, `source` (quel client — `manual`/`chatgpt`/`claude`/…, jamais fait/déduction), `confidence` (float libre), `approved: bool`. **Aucun champ `workspace`/`projet`** |
| Gouvernance | `main.py::reject_memory_shortcut` | Rejeter = `approved=False` — **identique à « pas encore approuvé »**. Un souvenir rejeté et un souvenir jamais relu sont indiscernables dans le modèle |
| Suppression | `database.py::delete` | Vraie suppression SQL, jamais un tombstone |
| Recherche vectorielle | `vector_store.py` | Qdrant + `sentence-transformers/all-MiniLM-L6-v2` **si disponibles** ; sinon repli **silencieux** (`except Exception: … self.mode = "hash"`, un `print()`, jamais remonté à l'appelant HTTP) vers un embedding maison (bag-of-mots haché, cosinus) — **les 12 tests du dépôt tournent tous avec `EMBEDDING_MODE=hash`** (`backend/tests/test_api.py::make_client`), donc le chemin Qdrant annoncé par le README n'est jamais vérifié par leur propre CI |
| Extraction de candidats | `suggestions.py` | Regex anglaises (projet/préférence/objectif/compétence/décision), jamais un modèle — chaque candidat porte `approved=False`, une `confidence < 1` et une `reason` |
| Import | `importers.py` | Détecte `.zip`/`.json`/`.txt`/`.md`, reconnaît l'export ChatGPT (`mapping`) et Claude (`chat_messages`) par leur forme JSON, jamais par extension seule |
| Ask Memory | `ask.py` | **Aucun appel à un LLM** : un gabarit de phrase (« Based on stored memories: … ») autour des souvenirs retrouvés — malgré le nom, ce n'est pas une synthèse générative |
| MCP | `mcp_server/server.py` | `FastMCP` (SDK MCP 1.x), 7 outils en HTTP+clé vers son propre backend : `search_memory`, `create_memory`, `list_memory`, `update_memory`, `approve_memory`, `reject_memory`, `ask_memory`, `delete_memory` |
| Chiffrement | `frontend/src/cryptoVault.js` | AES-256-GCM (Web Crypto), clé dérivée par PBKDF2-HMAC-SHA256, **310 000 itérations**, sel 16 octets et IV 12 octets tirés au hasard à CHAQUE chiffrement — **jamais utilisé côté backend local**, seulement pour le mode hébergé (Supabase) |
| Authentification locale | `auth.py::require_api_key` | `x_api_key == settings.api_key` — **comparaison `==`, pas à temps constant** (`secrets.compare_digest`) |
| Tests | `backend/tests/test_api.py` | 12 tests, réels (TestClient FastAPI), mais aucun n'exerce le chemin Qdrant/sentence-transformers ni un chiffrement quelconque côté backend |

## Ce qui n'a PAS pu être confirmé, ou est plus faible qu'annoncé

- **Aucune isolation de workspace/projet.** Le modèle `Memory` n'a pas de champ
  équivalent à `projet` — la mission (§16/§40) suppose une capacité qu'AI Memory
  Vault ne fournit pas ; ARENA l'avait déjà (`core/memory/personnelle.py::Souvenir.projet`,
  déjà branché dans `recuperer()`).
- **Rejeter n'est pas un état.** `reject_memory_shortcut` remet simplement
  `approved=False` — un souvenir rejeté redevient indiscernable d'un souvenir en
  attente, et pourrait être approuvé par erreur plus tard sans que rien ne dise
  qu'il avait été explicitement rejeté une fois.
- **Repli silencieux sur un faux embedding.** `VectorStore._init_qdrant` avale
  l'exception et bascule sur un hachage bag-of-mots sans jamais le dire à
  l'appelant — contraire à la discipline déjà en place dans
  `core/memory/semantique.py` (`mode="LEXICAL"` explicite, mesuré, jamais simulé).
- **Comparaison de clé non constante.** `auth.py` compare la clé d'API avec `==`.
  Risque mineur en pratique (canal HTTP local), mais `apps/backend/security.py`
  d'ARENA le fait déjà correctement (`_egales`, `secrets.compare_digest`) —
  aucune régression à introduire ici en le copiant.
- **`LICENSING.md` n'existe pas** pour ce dépôt-ci non plus (à la différence de
  Tunnet, DEC-0089, la licence globale MIT ne dépend d'aucun fichier manquant :
  vérifié directement dans `LICENSE`).

## Comparaison avec l'architecture ARENA existante (audit préalable, §3)

| Capacité | État ARENA avant cette mission | Verdict |
|---|---|---|
| Modèle de souvenir avec provenance | `core/memory/personnelle.py::Souvenir` — `Nature` (FAIT/PREFERENCE/INFERENCE/CONTEXTE_TEMPORAIRE), source obligatoire, projet, importance — **ACTIF**, déjà plus riche que le `Memory` d'AI Memory Vault | Étendu (`Etat`, `sensible`), jamais remplacé |
| Gouvernance (approbation) | `MemoirePersonnelle.confirmer()` — le seul chemin INFERENCE→FAIT, source obligatoire — **ACTIF** | Manquait `rejeter`/`archiver`/`reactiver`/`supprimer` — ajoutés ICI, dans le même fichier |
| Récupération bornée en tokens | `core/memory/recuperation.py::recuperer` — 4 signaux, budget dur en caractères, explication par résultat — **ACTIF**, déjà ce que la mission §10/§32 demande | Réutilisé tel quel par le routeur HTTP et le serveur MCP, jamais réécrit |
| Recherche sémantique locale | `core/memory/semantique.py` — embeddings Ollama, `mode="LEXICAL"` explicite si indisponible — **ACTIF**, déjà local-first (§11) sans dépendance cloud | Rien à changer — meilleur que le repli silencieux d'AI Memory Vault |
| Déduplication | `core/memory/consolidation.py::grouper`/`empreinte` — **ACTIF** | `empreinte()` réutilisé tel quel pour le pipeline d'import |
| Contexte projet (style OpenContext) | `core/context/instantane_projet.py` (DEC antérieure, mission ARENA×OPENCONTEXT) — **ACTIF** | Non touché — responsabilité distincte (contexte de dépôt de code, pas mémoire utilisateur), déjà séparée comme la mission §5 le demande |
| Recherche unifiée (mémoire+code+web+projet) | `core/context/recherche_unifiee.py` — **ACTIF** | Non touché — compose déjà `core/memory/` parmi ses sources |
| Masquage de métadonnées secrètes | `core/actions/journal.py::masquer` (par nom de champ) — **ACTIF** | Réutilisé tel quel dans `retenir()`/`enregistrer_entite()`, inchangé |
| Détection de secrets par forme | `scripts/scanner_secrets.py::MOTIFS_NOMMES` (clé AWS/Google/Slack/GitHub/Stripe/OpenAI, clé PEM) — **ACTIF**, pour les commits | Réutilisé tel quel (import direct) pour refuser un CONTENU de souvenir en forme de secret (§35) — jamais une seconde liste |
| Chiffrement au repos | **NOT_PRESENT** | Ajouté (`core/memory/chiffrement.py`) — AES-256-GCM + PBKDF2-HMAC-SHA256, paramètres égaux ou supérieurs à ceux vérifiés chez AI Memory Vault |
| Serveur MCP (ARENA exposée) | **NOT_PRESENT** — `core/mcp/` ne contenait qu'un CLIENT (WanGP, OpenTakeoff) | Ajouté (`core/mcp/memory_server.py`) — premier serveur MCP d'ARENA, une seule capacité (mémoire) |
| API HTTP dédiée à la mémoire | **NOT_PRESENT** — la mémoire n'était atteignable que via `/chat` | Ajouté (`apps/backend/routers/memory.py`) |
| Import de conversations externes | **NOT_PRESENT** | Ajouté (`core/memory/import_conversations.py`) |

**Aucun second système de mémoire, aucun second moteur de récupération, aucune
seconde base de vecteurs.** `core/memory/personnelle.py` reste l'unique table de
vérité ; le serveur MCP et le routeur HTTP l'appellent tous les deux, jamais une
copie.

## Ce qui a été adopté d'AI Memory Vault (idées, jamais code copié)

1. **Le choix des six outils MCP** (`search_memory`, `create_memory`,
   `list_memory`, `approve_memory`, `reject_memory`, `delete_memory`) — leur
   `update_memory`/`ask_memory` n'ont pas été repris (`ask_memory` n'apporte
   rien qu'un client MCP ne peut déjà faire avec `search_memory` + le routeur
   de modèles d'ARENA ; `update_memory` n'a pas de cas d'usage mesuré ici).
2. **Les paramètres de chiffrement** (AES-256-GCM, PBKDF2-HMAC-SHA256, sel et
   IV aléatoires par enregistrement) — portés en Python (`cryptography`,
   déjà présente transitivement dans ce dépôt), avec 600 000 itérations
   au lieu de 310 000 (voir `core/memory/chiffrement.py` pour le raisonnement).
3. **La détection de format d'import par la forme du JSON**
   (`mapping` → ChatGPT, `chat_messages`/`uuid` → Claude), pas par le nom du
   fichier seul.
4. **« Rejeter n'est pas juste ne-pas-approuver »** — identifié comme un
   MANQUE chez eux (voir plus haut), corrigé dans ARENA par un état
   `Etat.REJETE` distinct, jamais copié depuis leur code (ils ne l'ont pas).

## Ce qui a été explicitement rejeté

1. **Qdrant + sentence-transformers.** ARENA a déjà une recherche sémantique
   locale (`core/memory/semantique.py`, embeddings Ollama) — ajouter un second
   moteur vectoriel dupliquerait une capacité qui existe et fonctionne
   (mission §29/§30, interdiction explicite).
2. **Supabase / mode hébergé multi-tenant.** ARENA est un système
   personnel, mono-propriétaire (DEC-0009 et suivantes) — un backend
   Postgres+RLS partagé entre plusieurs comptes n'a pas de sens ici
   (mission §47/§48 : le contrat canonique reste celui d'ARENA, jamais
   redessiné autour de Supabase).
3. **L'extension navigateur.** Mission §24/§25 : jamais le fondement de la
   mémoire, et ARENA n'a aucune interface navigateur qui en aurait besoin
   aujourd'hui — non construite.
4. **`Ask Memory` comme second chatbot.** Leur implémentation n'appelle même
   pas un modèle (un gabarit de phrase) ; une vraie synthèse passe par le
   routeur de modèles d'ARENA lui-même (`core/models/`), jamais un second
   moteur de réponse — non construite séparément : `search_memory` +
   `core/memory/recuperation.py::rendre_ligne`/`formater` donnent déjà à
   n'importe quel agent ARENA de quoi répondre avec provenance.
5. **`update_memory` (édition libre du contenu).** Aucun besoin mesuré ; une
   correction passe par `rejeter()` + une nouvelle création, ce qui préserve
   l'historique (mission §27 : « ne jamais réécrire silencieusement une
   preuve historique » — éditer en place ferait exactement ça).

## Vérification

- **Chiffrement** : round-trip, mauvaise clé, tag GCM altéré, JSON corrompu —
  tous testés (`tests/core/test_memoire_chiffrement.py`, 17 tests) et sur le
  souvenir réel dans `MemoirePersonnelle` (`tests/core/test_memoire_gouvernance.py`,
  classe `TestChiffrementIntegre`) : le clair n'apparaît jamais dans le fichier
  SQLite, vérifié en lisant la ligne brute.
- **Gouvernance** (`Etat.REJETE`/`ARCHIVE`, `rejeter`/`archiver`/`reactiver`/
  `supprimer`) : testée, y compris la migration d'une base créée avant cette
  mission (`TestMigrationDUneBaseExistante`).
- **Persistance après redémarrage** (mission §39/§43) : trois scénarios réels
  — un fait approuvé, un souvenir rejeté, un souvenir sensible — chacun écrit
  par une instance `MemoirePersonnelle`, l'instance détruite, une **nouvelle**
  instance ouverte sur le même fichier, sans étape de restauration manuelle
  (`TestPersistanceApresRedemarrage`).
- **Isolation de projet** (mission §16/§40) : deux projets, deux réponses
  différentes à « quelle base de données ce projet utilise-t-il ? », zéro
  contamination croisée (`TestIsolationDeProjet`).
- **Efficacité en tokens** (mission §32) : mesurée, pas supposée — 51 souvenirs
  écrits, un seul pertinent, **réduction de plus de 90 % des caractères
  envoyés** par rapport à « tout le contexte » (`TestEfficaciteTokens`).
- **Import** : ChatGPT (ZIP + JSON), Claude (JSON), texte brut ; déduplication
  contre un import répété ET contre la mémoire déjà présente ; un contenu en
  forme de secret refusé plutôt que stocké ; une injection de prompt
  (« Ignore previous instructions... ») importée reste une CHAÎNE DE
  CARACTÈRES dans le contenu d'un souvenir `INFERENCE` — jamais exécutée, par
  construction (`core/memory/import_conversations.py` n'importe aucun module
  de `core/models/`, vérifiable en le lisant) (`tests/core/test_memoire_import_conversations.py`,
  20 tests).
- **Serveur MCP** : les six outils appelés directement (12 tests), **et** un
  vrai sous-processus parlé par le protocole JSON-RPC stdio réel via
  `core/mcp/stdio_transport.py::ClientMcpStdio` (le même client qu'ARENA
  utilise déjà pour OpenTakeoff) — deux appels en séquence, `tools/list`
  vérifié contre les six noms attendus (`tests/core/test_mcp_memory_server.py`).
- **API HTTP** : create/search/approve/reject/archive/reactivate/delete/
  export/import, l'authentification (401 sans clé), les 404, tout via
  `TestClient` contre l'application FastAPI réelle, jamais une route
  simulée (`tests/test_memory_router.py`, 17 tests).
- **Régression complète** : voir `docs/DECISIONS.md`, DEC-0090.

## Ce que ça coûte si c'est faux

Le coût d'avoir sous-estimé une capacité d'AI Memory Vault serait de refaire
plus tard un travail déjà fait ailleurs (peu probable : leur backend local est
petit, entièrement lu). Le coût réel est ailleurs : le serveur MCP est le
premier de son genre dans ce dépôt, jamais éprouvé contre un client MCP
externe réel (Claude Desktop, Cursor) — seulement contre le client stdio
qu'ARENA possède déjà et contre les fonctions Python directement. S'il existe
un écart de conformité au protocole que ce client-là ne révèle pas, il ne sera
découvert qu'au premier usage réel. Documenté, pas masqué.
