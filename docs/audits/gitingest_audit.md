# Audit — GitIngest comme capacité d'ingestion de dépôt

*Demandé le 05/09/2026 : intégrer GitIngest (coderamp-labs) comme capacité
d'ingestion de code/contexte d'ARENA. Mesuré, pas lu dans une description —
le dépôt amont a été cloné et sa version réellement installée testée sur un
fixture jetable et sur ce dépôt lui-même.*

---

## 1. Provenance (équivalent SOURCE.md)

| | |
|---|---|
| Dépôt officiel | https://github.com/coderamp-labs/gitingest |
| Révision inspectée | `4e259a02fe72115bee538271622f1234a81c8e1a` (2025-08-16) |
| Version PyPI intégrée | `gitingest==0.3.1` (correspond à la révision inspectée) |
| Date d'intégration | 2026-09-05 |
| Licence vérifiée | **MIT** (`LICENSE`, « Copyright (c) 2024 Romain Courtois ») — confirmée sur cette révision |
| Distribution | Paquet PyPI officiel `gitingest`, installé directement (`requirements.txt`) — **aucun code source copié ou vendu** dans ce dépôt. Même mécanisme que `pypdf`/`python-docx`, pas celui d'un service cloné à part. |
| Ce qui est intégré | L'API Python publique (`gitingest.ingest_async`), utilisée directement — jamais par sous-processus/CLI. |
| Ce qui reste externe | Le code source de GitIngest, son extra `[server]` (FastAPI/uvicorn/boto3/Prometheus — un serveur web autonome) — **non installé** : ARENA est déjà le serveur. |
| Modifications | Aucune. Utilisé strictement via son API publique documentée. |

## 2. Ce que le paquet fait réellement (mesuré)

Bibliothèque Python pure, dépendances légères : `click`, `gitpython`, `httpx`,
`loguru`, `pathspec`, `pydantic`, `python-dotenv`, `starlette`, `tiktoken`.
`ingest_async(source, ...)` accepte un chemin local **ou** une URL Git, et
rend `(résumé, arbre, contenu)` — trois chaînes. `.gitignore` respecté par
défaut (`include_gitignored=False`). Le clone temporaire d'une source
distante est écrit sous `tempfile.gettempdir()/gitingest/<uuid>/` puis
**nettoyé par la bibliothèque elle-même** (`shutil.rmtree`, vérifié dans
`gitingest.entrypoint`) — rien ne reste sur le disque au-delà de l'appel,
sauf en cas d'échec réseau avant tout contenu écrit (vérifié : le résidu est
un dossier vide de 4 Ko, négligeable).

## 3. Deux défauts réels trouvés en écrivant le connecteur

**Aucun n'était visible en lisant seulement la documentation amont.**

1. **Un jeton GitHub égaré casse une ingestion purement locale.**
   `gitingest.utils.auth.resolve_token(token)` retombe sur
   `os.environ["GITHUB_TOKEN"]` dès qu'aucun jeton n'est fourni
   explicitement — **même pour un répertoire local qui n'en a besoin
   d'aucun** — et lève `InvalidGitHubTokenError` si sa forme ne ressemble pas
   à un vrai jeton GitHub. Mesuré : un `GITHUB_TOKEN` présent dans ce
   conteneur pour une tout autre raison faisait échouer l'ingestion d'un
   simple dossier de test. Corrigé : `_sans_jeton_errant()` retire
   temporairement la variable de l'environnement pour tout appel qui ne
   fournit pas explicitement de jeton.
2. **`asyncio.run()` plante depuis une route déjà async.**
   `registre.executer(...)` est appelé en clair (sans `await`) depuis des
   routes FastAPI et des agents déjà `async def` — donc déjà sous la boucle
   d'uvicorn (vérifié : `apps/backend/routers/chat.py`,
   `agents/plaquiste/plaquiste_agent.py`). Une première version de
   `_ingerer()` appelait `asyncio.run()` directement, qui lève
   `RuntimeError: cannot be called from a running event loop` dans ce
   contexte réel. Corrigé : un thread dédié (`ThreadPoolExecutor`) obtient
   sa propre boucle, sans toucher à celle qui tourne déjà. Sabotage-vérifié :
   revenir à `asyncio.run()` direct fait échouer
   `test_ingestion_locale_depuis_une_boucle_asyncio_deja_active`.

## 4. Ce qui n'a PAS été branché, et pourquoi

- **`include_gitignored=True` (bascule pour inclure les fichiers exclus)** :
  jamais exposée. L'exposer contournerait exactement ce que la protection
  par chemin (§5) et `.gitignore` protègent déjà — `.env`, caches, secrets
  qu'un dépôt exclut lui-même. `SUGGESTION — NON IMPLÉMENTÉE`.
- **Ingestion de dépôts privés** : le paramètre `jeton` existe et est
  transmis à GitIngest si fourni explicitement par l'appelant, mais ARENA ne
  gère aujourd'hui aucun jeton GitHub propre (vérifié : aucune trace de
  `GITHUB_TOKEN`/`GH_TOKEN` dans `apps/backend/config.py` ni ailleurs). Sans
  jeton fourni, un dépôt privé échoue proprement (`ECHEC`, message clair) —
  jamais un faux succès.
- **Extra `[server]`** : non installé, ARENA est déjà le serveur.

## 5. Ce qui protège les chemins locaux sensibles

Un segment de chemin (`.ssh`, `.aws`, `.gnupg`, `.git-credentials`,
`.netrc`, une clé privée nommée) ou un nom de fichier (`.env`,
`credentials.json`, `secrets.json`) refuse l'ingestion **avant même
d'ouvrir quoi que ce soit** — vérifié sur `~/.ssh`, `~/.aws/credentials`,
`~/.gnupg`, un `.env` dans un sous-dossier arbitraire. `.gitignore` protège
ce qu'un dépôt exclut lui-même ; ceci protège ce qu'aucun `.gitignore` ne
verra jamais parce que le chemin vise directement ce dossier.

## 6. Mesuré pour de vrai, sur un fixture jetable

```
README.md, module.py, config.yaml, .gitignore (excluant secret.txt)
→ 3 fichiers retenus, secret.txt absent de l'arbre ET du contenu,
  module.py present avec son vrai code.
```

Vérifié aussi depuis une vraie boucle asyncio active (le chemin d'appel réel
de production) et avec un `GITHUB_TOKEN` invalide dans l'environnement
(l'ingestion locale aboutit quand même).

## 7. Un blocage réel de cet environnement, honnêtement rapporté

L'ingestion d'une **URL GitHub réelle** (`https://github.com/octocat/...`)
n'a pas pu être vérifiée bout en bout **depuis ce conteneur** : la politique
réseau de ce bac à sable renvoie `403 Forbidden` sur un simple
`curl -I https://github.com/...` — confirmé avec `curl` nu, indépendamment
de GitIngest. Le chemin de code est réel et utilise la même fonction
(`ingest_async`) vérifiée ci-dessus ; seule cette vérification réseau
précise reste bloquée par l'environnement de test, pas par le code. Sur la
machine d'Ousmane (accès Internet normal), rien n'indique que ce blocage
existerait.
