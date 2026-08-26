# CHANGELOG - ARENA PERSONAL AI

## [Non publié]
### Sécurité
- La clé de la passerelle ne figure plus dans le dépôt : `librechat.yaml` lit
  `${ARENA_API_KEY}`, que `docker-compose.yml` transmet au conteneur LibreChat.
- Les endpoints métier `/api/upload`, `/api/process-video`, `/api/chat` et
  `/api/chat/stream` exigent la même clé Bearer que `/v1`. Ils étaient ouverts.
- CORS restreint aux interfaces locales (`ARENA_ALLOWED_ORIGINS`) au lieu de `*`,
  méthodes limitées à `GET`/`POST`. Combiné aux endpoints ouverts, `*` laissait
  n'importe quel site appeler les agents depuis le navigateur.
- L'interface `apps/frontend/index.html` envoie la clé et l'oublie si elle est refusée.
- Le bac à sable ne dégrade plus : sans Docker, l'exécution de code est
  **refusée** (`sandbox_mode: REFUSED`) au lieu de basculer sur la machine hôte.
  Le repli reste possible derrière `ALLOW_UNSAFE_EXEC=true`, explicitement.
- `CoderAgent` ne relance plus le modèle pour corriger un code refusé : ce
  n'est pas le code qui a échoué. Il renvoie `status: refused`.
- `EXECUTE_COMMANDS` passe à `false` par défaut, dans `config/permissions.yaml`
  **et** dans `DEFAULT_PERMISSIONS` — un `permissions.yaml` introuvable retombait
  sinon sur la valeur permissive. `.env.example` annonçait aussi l'inverse.

### Déploiement
- `requirements.txt` ne contient plus que les 12 dépendances réellement importées
  par le code. Le `pip freeze` d'origine est conservé dans `requirements.lock.txt`.
- `pywin32` retiré des dépendances directes : plus aucun import ne le référence, et
  il faisait échouer le build Docker Linux. Il garde un marqueur
  `sys_platform == "win32"` dans le lock.
- `langchain-openai` épinglé en `1.1.9` : la `1.6.0` du lock exige `openai>=2.45`
  alors que `browser-use==0.13.8` épingle `openai==2.16.0`. Le couple gelé était
  déjà impossible à réinstaller.

### Tests
- Socle pytest exécutable hors ligne : `tests/conftest.py` fournit un `FakeProvider`
  scripté (aucun réseau, réponses données à l'avance, appels enregistrés) et une
  mémoire SQLite jetable par test. `pyproject.toml` configure pytest, `asyncio_mode`
  et le marqueur `integration`, désélectionné par défaut.
- `requirements-dev.txt` ajoute `pytest` et `pytest-asyncio`.

## [1.7.0] - 2026-08-25
### Sécurité
- La passerelle `/v1` exige désormais une clé API (`ARENA_API_KEY` dans `.env`).
  Sans elle, toute requête est refusée (401).
- Validation stricte des chemins vidéo : un fichier hors du dossier `media/`
  est refusé, sur `/api/chat` comme sur `/api/process-video`.
- Bac à sable Docker opérationnel : le code généré par l'IA s'exécute dans
  l'image `arena-sandbox`, sans accès au disque ni à Internet.
- Secrets LibreChat et Open WebUI sortis de `docker-compose.yml` vers `.env`,
  et intégralement renouvelés.
- Les erreurs 403 ne sont plus transformées en 500.

### Corrigé
- LightRAG : chemin d'import corrigé et passage au modèle `nomic-embed-text`.
- GraphRAG : utilise l'image `arena-graphrag` (qui contient réellement GraphRAG)
  au lieu d'une image Python vide.
- SWEAgent : la recherche dans le dépôt utilisait le premier mot de la phrase.
  Elle cible maintenant le nom de fichier cité ou le mot le plus significatif.
- Les agents spécialisés se choisissent dans le menu de LibreChat, et non plus
  par détection de mots courants ("projet", "document"...).
- Connexions SQLite refermées après chaque usage.
- L'adresse d'Ollama et les noms de modèles sont lus depuis `.env`.
- Encodage des accents réparé dans `README.md` et les fichiers `docs/`.

### Maintenance
- Base MongoDB retirée du suivi Git et purgée de l'historique (`.git` : 822 Mo -> 0).
- `requirements.txt` régénéré : 17 -> 174 dépendances réelles.
- Suppression des scripts jetables qui pouvaient écraser le code source.
- Tests : le faux `test_orchestrator.py` (copie du code source) est remplacé par
  un vrai test ; `test_sandbox.py` échoue désormais quand la protection est absente.

### Limites connues
- GraphRAG est prêt mais nécessite l'ajout de documents puis une indexation.
- `SWEAgent` et `RepoEngineerAgent` analysent et proposent : ils ne modifient
  aucun fichier.
- Les deux modèles Ollama (15,6 Go) dépassent les 12 Go de VRAM de la carte :
  Ollama alterne leur chargement.

## [1.6.0] - 2026-08-25
### Ajouté
- Integration de SWEAgent (Princeton NLP ACI Pattern).
- Integration de RepoEngineerAgent (Odysseus / Devin Multi-file Pattern).
- Integration de Browser-Use & Playwright (Navigation Web Autonome).
- Integration de Microsoft GraphRAG & LightRAG (Graphes de Connaissances).
- Integration d'OpenSandbox (Bac a sable Docker isole).
- Integration des interfaces LibreChat (:3080) et Open WebUI (:3000).
