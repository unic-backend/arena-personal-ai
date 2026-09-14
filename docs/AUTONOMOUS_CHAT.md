# Chat autonome : installation et contrat

Cette livraison ajoute `POST /api/v1/chat`. Les routes `/agent/stream`,
`/api/chat`, `/api/chat/stream` et `/v1/chat/completions` gardent leurs contrats.
La PWA existante utilise encore `/agent/stream` : elle ne bascule pas
automatiquement sur la nouvelle route.

## Audit avant implementation

Base de travail : `4a66e0c`, branche `main`, relevee le 13 septembre 2026.

- Le backend est `apps/backend/`, avec les composants dans `core/` et `agents/`.
  Il n'existe pas de paquet `backend/models` ou `backend/services` a conserver.
- Pas de modele ORM `User`, `Conversation` ou `Message`, pas de session
  SQLAlchemy, pas d'Alembic : SQLite via connexions courtes et transactions.
- `MemoryManager` porte `short_term_memory` (session, role, contenu) et
  `long_term_memory` (profil). `MemoirePersonnelle` porte les souvenirs types.
  `DepotConversations` porte la synchronisation des conversations de la PWA.
- `verify_api_key` controle `Authorization: Bearer <USMAN_API_KEY>`.
  C'est l'identite d'un proprietaire unique, pas un JWT multi-utilisateur.
- Le nouveau `current_user` reutilise cette dependance. Le corps JSON ne
  peut fournir ni `user_id`, ni role systeme, ni historique privilegie.

## Fichiers

| Fichier | Responsabilite |
|---|---|
| `apps/backend/services/settings.py` | Configuration validee |
| `apps/backend/services/ai_client.py` | AsyncOpenAI, Ollama compatible, confidentialite, compteur cloud |
| `apps/backend/services/memory_engine.py` | Historique SQLite, Chroma, extraction et reprise |
| `apps/backend/services/tools/registry.py` | Schemas et validation des appels |
| `apps/backend/services/tools/builtin.py` | Calcul AST borne, recherche HTTP |
| `apps/backend/services/orchestrator.py` | Contexte dynamique et boucle de cinq tours |
| `apps/backend/routers/autonomous_chat.py` | Authentification et route Pydantic |
| `apps/backend/main.py` | Inclusion du routeur, demarrage/arret du worker |
| `apps/backend/Dockerfile` | Chroma dans le volume de donnees du conteneur |
| `tests/test_autonomous_chat.py` | Tests comportementaux, dont Chroma reel hors ligne |
| `tests/test_surface_api.py` | Contrat HTTP existant et nouvelle route |
| `.github/workflows/ci.yml` | Installation des nouvelles dependances de test |
| `requirements.txt`, `.env.example`, `.gitignore` | Installation et donnees locales |

## Installation

Dans l'environnement Python du projet : `python -m pip install -r requirements.txt`.
Nouvelles dependances directes : `openai==2.26.0` (version deja imposee par
browser-use) et `chromadb==1.5.9`. Le gel historique `requirements.lock.txt`
documente deja ses incompatibilites : cette livraison ne le regenere pas a
partir d'un environnement different de celui du proprietaire.

| Variable | Defaut / usage |
|---|---|
| `USMAN_API_KEY` | Authentification existante, obligatoire |
| `OPENAI_API_KEY` | Optionnelle ; chat OpenAI et embeddings |
| `USMAN_AUTONOMOUS_MODEL` | `gpt-4.1-mini`, remplacable par un modele compatible tools |
| `USMAN_AUTONOMOUS_TIMEOUT` | 30 secondes maximum par tentative de fournisseur |
| `USMAN_AUTONOMOUS_CONTEXT_CHARS` | 24000 caracteres, borne totale de contexte |
| `USMAN_CHROMA_PATH` | `chroma_db` a la racine ; `/app/data/chroma_db` dans Docker |
| `TAVILY_API_KEY` | Optionnelle ; sinon DuckDuckGo Instant Answer |
| `OLLAMA_BASE_URL`, `CHAT_LOCAL_MODEL` | Reglages locaux deja existants |
| `AI_LOCAL_ONLY`, `AI_CLOUD_ENABLED`, `AI_MODE` | Politique existante, toujours prioritaire |

Les embeddings utilisent `text-embedding-3-small`. Ils sont envoyes a OpenAI
uniquement si une cle est presente ET si la politique de confidentialite
l'autorise. En mode local seul, la memoire utilise SQLite et le chat utilise
Ollama. Les textes identifies comme tres sensibles ne sont pas envoyes a OpenAI.
La recherche web est un outil reseau explicite, distinct du mode d'inference
locale ; elle refuse aussi les requetes identifiees comme secrets.

Les appels chat, extraction et embeddings alimentent le compteur cloud
existant. Le plafond de nombre de requetes est partage. Comme dans le
compteur d'origine, le cout monetaire est **non verifiable** tant qu'aucun
tarif n'est configure : aucun montant gratuit ou budget garanti n'est invente.

## Appel HTTP

Envoyer un POST authentifie a `/api/v1/chat`, avec `Content-Type: application/json` :

```json
{
  "message": "Calcule 84 fois 2500, puis 80 % du total.",
  "conversation_id": "50c82a06-6f06-40c6-96ef-1d581da93484"
}
```

`conversation_id` est un UUID : le conserver pour reprendre le meme fil.
L'omettre cree un nouveau fil et retourne son identifiant. `message` accepte
de 1 a 8000 caracteres, hors message compose uniquement d'espaces. Les champs
inconnus sont refuses (422). Cle absente ou invalide : 401 ; cle serveur non
configuree : comportement existant, 500. Limitation de debit : 429.

La reponse contient `conversation_id`, `response`, `status`, `iterations`,
`tools`, `warnings`, `memory_saved`. `status` vaut `success`, `degraded` ou
`unavailable`. Le texte reste explicite quand aucun modele ne repond.
`memory_saved=true` prouve la sauvegarde SQLite et la mise en file de
l'extraction, **pas** son achevement ni la disponibilite de Chroma.
La route est synchrone au sens HTTP (une reponse JSON), entierement asynchrone
pour le serveur ; elle ne pretend pas streamer.

## Flux et stockage

1. Charger l'historique du fil avec une cle derivee de l'identite serveur et
   de l'UUID. Lire les faits du proprietaire et les souvenirs pertinents.
   Les souvenirs historiques de `MemoirePersonnelle` sont egalement consultes
   pour le proprietaire ; ils ne sont pas reindexes automatiquement dans Chroma.
   Les souvenirs selectionnes font partie du contexte du modele et suivent
   la meme politique de confidentialite que ce contexte. Un souvenir ancien
   marque sensible impose Ollama et bloque les outils externes. Cet echange
   n'est pas recopie dans le stockage en clair ni indexe ; la reponse annonce
   `sensitive_exchange_not_persisted` et `memory_saved=false`.
2. Construire le prompt avec un budget borne et les roles des messages.
   Les souvenirs restent des donnees, les anciennes reponses des inferences.
3. Jusqu'a cinq tours de modele ; au plus quatre outils par tour. Le dernier
   tour est reserve a la synthese. Une sortie d'outil porte l'identifiant
   exact de l'appel. Aucun outil n'est charge depuis un chemin du modele.
4. Sauvegarder les deux messages entiers dans `short_term_memory` et creer
   le travail de consolidation dans **la meme transaction**.
5. Extraire en arriere-plan des citations utilisateur verifiables, pas des
   affirmations de l'assistant. Deduplication par proprietaire/type/contenu.
   Indexer les messages par fragments de 1500 caracteres, sans perdre la fin.

Tables additives dans `USMAN_DB_PATH` : `autonomous_documents` (projection
recherchable et faits `user_fact`) et `autonomous_memory_jobs` (travaux repris).
Les anciens schemas ne sont ni renommes ni effaces. Les nouveaux faits vivent
dans cette projection ; l'ancienne route `/api/memory` conserve son perimetre
historique. Il n'y a pas de migration automatique des anciens fils PWA vers
les nouveaux identifiants de session.

Chroma utilise une collection liee au modele d'embedding, avec filtrage
obligatoire `user_id`. SQLite revalide ensuite chaque resultat. Une panne
Chroma ou OpenAI laisse les documents source intacts et utilise le rappel
SQLite. Un document interdit au cloud ne bloque pas l'indexation des suivants.

Le worker reprend les travaux a chaque demarrage et effectue des lots bornes.
Un bail SQLite empeche deux workers de reclamer simultanement le meme travail.
Apres trois echecs d'extraction, le travail reste en base avec `status=failed` ;
il n'est pas presente comme termine. Il peut etre remis a `pending` avec
`attempts=0`, `due=0`, `lease_until=0` par une intervention administrative
apres correction du fournisseur. L'indexation reste independante de cette
limite d'extraction et est retentee.

## Limites d'exploitation explicites

- Utiliser **un worker Uvicorn**, comme le Dockerfile existant : les tours
  d'une conversation sont serialises dans ce processus. Une execution
  multi-processus du chat demanderait un verrou de conversation distribue.
- Le contexte est borne en caracteres, pas tokenise pour chaque modele.
  Choisir une fenetre Ollama suffisante pour le budget configure.
- `calculate` utilise une arithmetique flottante bornee (`precision=float64`),
  pas un moteur de comptabilite decimale ou de calcul symbolique.
- DuckDuckGo Instant Answer n'est pas un moteur complet d'actualites. Le
  fallback annonce `limited_coverage=true`; zero source n'est jamais un succes.
- Les nouveaux outils sont en lecture/calcul. Ajouter `file_manager` ou
  `code_executor` doit reutiliser les permissions et bacs a sable existants,
  pas executer directement un nom de fonction choisi par le modele.
- Sauvegarder ensemble la base SQLite et le repertoire Chroma. Les nouveaux
  messages, comme l'historique SQLite existant, ne sont pas chiffres par ce
  service. Le chiffrement de volume reste un choix d'exploitation.
- Les appels OpenAI, Tavily et Ollama reels doivent etre testes avec les
  services configures. Les tests scripts ne mesurent pas l'intelligence du
  modele et ne prouvent aucune equivalence avec Claude ou GPT.

## Verification

`python -m pytest tests/test_autonomous_chat.py tests/test_surface_api.py -q`
teste les outils, l'authentification, la validation du corps, l'isolation,
les reprises, les pannes et le contrat HTTP. Les modeles et appels web sont
simules explicitement ; SQLite et Chroma ecrivent dans de vrais dossiers
temporaires. `python -m ruff check .` et la suite `python -m pytest tests/ -q`
restent les controles de regression du depot.


## Verification du 13 septembre 2026

33 nouveaux tests couvrent les outils, SQLite, la persistance Chroma reelle,
l'isolation utilisateur, la reprise d'extraction, les quotas partages,
l'authentification et la protection des souvenirs sensibles. Les reponses LLM
et HTTP sont simulees ; aucun succes OpenAI/Tavily/Ollama reel n'est presume.
Ruff et `git diff --check` passent. Le test d'isolation echoue bien lorsque
les namespaces sont volontairement fusionnes dans un processus jetable.

La suite complete hors reseau a rendu 5571 reussites, 54 skips et 52 tests
deselectionnes, avec quatre echecs ensuite resolus (documentation, noms de
variables et PATH de l'environnement de verification). Le controle final
cible couvre 151 tests, tous verts. Pas de nouvelle execution integrale apres
ces corrections ; pas encore de resultat de CI distante ni de deploiement.
