# ARENA — Engineering Worklog

Document de travail permanent du projet ARENA Personal AI.
Il survit aux sessions : toute personne — humaine ou IA — qui reprend le projet
doit pouvoir comprendre ici ce qui a été fait, ce qui reste, et pourquoi.

**Règle de tenue** : une tâche n'est marquée `TERMINÉ` qu'après une vérification
exécutée et dont le résultat est recopié ici. Une modification de fichier réussie
n'est pas une preuve que la fonctionnalité marche.

Dernière mise à jour : **26 août 2026** — audit initial.

---

## PROJECT STATUS

| | |
|---|---|
| **Version courante** | 1.7.0 |
| **Branche de travail** | `claude/arena-personal-ai-qh66ix` (14 commits d'avance, non fusionnée) |
| **Branche de base** | `master` (30 commits, tête `00e8f4f`) |
| **Phase de développement** | Phase 7 bis — correction sécurité et fiabilité |
| **Suite de tests** | 125 tests hors ligne verts, 17 marqués `integration` |
| **Lint** | `ruff check .` → 0 erreur |

### Architecture actuelle

```
core/       socle : BaseAgent, ModelProvider, MemoryManager, PermissionManager, ReasoningEngine
agents/     12 agents spécialisés, tous héritant de BaseAgent
tools/      audio, browser, code, coder, rag, search, video
apps/backend/   API FastAPI (459 lignes) — point d'entrée unique
apps/frontend/  tableau de bord HTML mono-fichier
social/     connecteurs réseaux (TikTok en simulation)
tests/      suite pytest, FakeProvider, marqueur integration
docs/       suivi projet historique
documents/  ce document
```

**Note sur les noms de dossiers** : le prompt de référence parle de
`applications/`, `configuration/` et `documents/`. Les dossiers réels sont
`apps/`, `config/` et `docs/`. Seul `documents/` a été créé, pour ce worklog.

### Chaîne d'exécution d'une demande

```
Client (LibreChat, Open WebUI, tableau de bord)
  → /v1/chat/completions  ou  /api/chat
  → verify_api_key
  → OrchestratorAgent.analyze_intent    (1 appel au modèle rapide)
  → agent spécialisé  ou  génération directe
  → réponse
```

### Limitations connues, à ce jour

1. **Le chat ne va jamais chercher d'information fraîche sur le web.** La
   recherche existe (`WebSearchTool`) mais n'est atteignable que via
   `TrendAnalyzer` et `DeepResearcher`. Une question d'actualité posée en chat
   est répondue de mémoire par le modèle.
2. **Des faits sont figés dans le prompt système** (`get_arena_system_prompt`) :
   « Année actuelle : 2026 », le président et le premier ministre du Sénégal.
   Écrire une date dans un prompt ne donne pas de connaissance à jour.
3. **Budget VRAM dépassé sur le papier** : deux modèles déclarés,
   `qwen2.5-coder:14b` (~9 Go) et `qwen3.5:9b` (~6,6 Go), pour 12 Go de VRAM.
   Non mesuré — voir *PERFORMANCE*.
4. **Le tag `qwen3.5:9b` n'a pas été vérifié.** S'il n'existe pas, Ollama
   retombe silencieusement sur autre chose.
5. **Aucune mémoire sémantique.** SQLite stocke l'historique et des faits ;
   rien ne récupère par similarité. GraphRAG et LightRAG sont branchés mais
   aucun document n'est indexé.
6. **`main.py` mélange configuration, routage et logique métier** (459 lignes,
   8 routes).
7. **Le dépôt est public** et l'ancienne clé (`arena-saer-****`) reste dans l'historique
   Git au commit `00e8f4f`.

---

## COMPLETED

### 26 août 2026 — Correctifs de sécurité et de fiabilité (9 commits)

Branche `claude/arena-personal-ai-qh66ix`. Chaque entrée correspond à un commit.

---

**1. `fb83e98` — La clé API sort du dépôt**
*Fichiers* : `librechat.yaml`, `docker-compose.yml`, `.env.example`, `README.md`
*Changement* : la clé écrite en clair sous `apiKey:` est remplacée par `${ARENA_API_KEY}` ;
`docker-compose.yml` transmet la variable au conteneur LibreChat — elle manquait,
donc l'interpolation aurait donné une chaîne vide.
*Pourquoi* : secret en clair dans un dépôt public (V-01).
*Vérification* : recherche de la valeur exacte dans l'arbre de travail → aucune
occurrence ; `docker compose config` → la variable est bien interpolée dans le service `librechat`.
*Résultat* : **PARTIEL** — le fichier est propre, l'historique Git ne l'est pas.
Voir *DISCOVERED PROBLEMS · P-01*.

---

**2. `1116e27` — Authentification sur `/api/*` et CORS restreint**
*Fichiers* : `apps/backend/main.py`, `apps/frontend/index.html`, `.env.example`
*Changement* : les quatre routes `/api/upload`, `/api/process-video`,
`/api/chat`, `/api/chat/stream` dépendent de `verify_api_key`. CORS passe de
`["*"]` à une liste lue dans `ARENA_ALLOWED_ORIGINS`, méthodes `GET`/`POST`.
Le tableau de bord envoie la clé (saisie une fois, oubliée si refusée).
*Pourquoi* : V-02 + V-03. Combinés, n'importe quelle page web ouverte dans le
navigateur pouvait faire exécuter du code sur la machine.
*Vérification* : requêtes réelles via `TestClient` — sans clé : 401 sur les 4
routes ; mauvaise clé : 401 ; bonne clé : l'auth n'est plus la cause du refus ;
préflight depuis une origine externe : `access-control-allow-origin` absent.
*Résultat* : **TERMINÉ**

---

**3. `6063a46` — Le bac à sable refuse au lieu de dégrader**
*Fichiers* : `tools/code/sandbox_interpreter.py`, `agents/coder/coder_agent.py`,
`tests/tools/test_sandbox.py`, `.env.example`
*Changement* : les **deux** chemins de repli (Docker inactif, échec du conteneur)
renvoient `sandbox_mode: "REFUSED"`. Le repli sur l'hôte n'existe plus que
derrière `ALLOW_UNSAFE_EXEC=true`. Toute valeur non reconnue vaut « non ».
`CoderAgent` ne relance plus le modèle pour corriger un code refusé.
*Pourquoi* : V-04. Le code généré par le modèle s'exécutait sur l'hôte Windows
sans isolation dès que Docker était arrêté.
*Vérification* : Docker réellement inactif sur la machine de test. Code écrivant
un fichier témoin → `REFUSED`, fichier **non créé**. Avec le flag → exécuté,
fichier créé. `'', 'false', '0', 'peut-etre'` → tous `REFUSED`.
*Résultat* : **TERMINÉ**

---

**4. `8fb6475` — `EXECUTE_COMMANDS` bloqué par défaut**
*Fichiers* : `config/permissions.yaml`, `core/permissions/permission_manager.py`,
`.env.example`, `tests/core/test_permissions.py`
*Changement* : `false` dans le YAML **et** dans `DEFAULT_PERMISSIONS`.
*Pourquoi* : V-05. Le chemin `config/permissions.yaml` est relatif au répertoire
courant : lancer le backend depuis ailleurs retombait sur la valeur permissive.
Corriger le seul YAML n'aurait pas suffi.
*Vérification* : YAML introuvable → `EXECUTE_COMMANDS = False` ; YAML du dépôt →
`False` ; `WRITE_FILES` reste `True`.
*Résultat* : **TERMINÉ** — mais voir *P-05* : ce drapeau ne protège rien encore.

---

**5. `18b15ac` — `requirements.txt` portable**
*Fichiers* : `requirements.txt`, `requirements.lock.txt` (nouveau), `docs/CHANGELOG.md`
*Changement* : 174 lignes de `pip freeze` → 12 dépendances directes, dérivées en
parsant chaque `.py` avec `ast`. Le gel d'origine est conservé en
`requirements.lock.txt`. `pywin32` retiré (aucun import dans le code).
`langchain-openai` épinglé en `1.1.9`.
*Pourquoi* : `pywin32==312` n'a pas de distribution Linux — le build Docker ne
pouvait pas aboutir.
*Vérification* : `pip install --dry-run -r requirements.txt` → OK sur Python
3.11 (version du Dockerfile) et 3.12 ; `pip download pywin32==312` sur Linux →
*No matching distribution found* ; `langchain-openai 1.1.9 + openai 2.16.0` →
`ChatOpenAI` importé et instancié avec les arguments qu'ARENA lui passe.
*Résultat* : **TERMINÉ**
*Découverte* : l'environnement Windows figé **n'est pas réinstallable** —
`langchain-openai 1.6.0` y cohabite avec un `openai` qu'il n'accepte pas, et
`numpy==2.5.2` exige Python ≥ 3.12 alors que le Dockerfile part de 3.11.

---

**6. `c197a2c`, `83212c0`, `7d37896`, `aa7f5dc`, `5586955` — Suite de tests**
*Fichiers* : `tests/conftest.py` (nouveau), 21 fichiers de tests réécrits,
`pyproject.toml`, `requirements-dev.txt`
*Changement* : `FakeProvider` scripté (aucun réseau, réponses données à l'avance,
appels enregistrés, erreur explicite sur un appel non prévu). Marqueur
`integration` pour tout ce qui exige Ollama, Docker, ffmpeg, Whisper, Chromium
ou le réseau, désélectionné par défaut.
*Pourquoi* : les tests étaient des scripts `print()`. **Dix fichiers sur 21 ne
définissaient qu'un `main()`, jamais collecté par pytest** — ils ne testaient
rien. `tests/test_memory_chat.py` n'affirmait rien du tout.
*Vérification* : `pytest` → **125 passed, 17 deselected** ; `pytest -m
integration` → 17 skipped, 0 failed, chacun nommant le service manquant.
État de départ mesuré : 12 passed, 2 failed.
*Résultat* : **TERMINÉ**

---

**7. `5931ddd` — ruff**
*Fichiers* : `pyproject.toml`, 49 fichiers corrigés
*Changement* : jeu de règles `E4, E7, E9, F, W, I, B`. 178 corrections
automatiques, 5 manuelles.
*Vérification* : `ruff check .` → *All checks passed* ; `pytest` → 103 passed
après les corrections ; les 40 modules importables s'importent toujours.
*Résultat* : **TERMINÉ**

---

**8. `0f237c0` — LICENSE, CI, `.dockerignore`**
*Fichiers* : `LICENSE`, `.github/workflows/ci.yml`, `.dockerignore`, `README.md`
*Changement* : licence propriétaire, tous droits réservés (décision du
propriétaire). CI à deux jobs : lint + suite hors ligne sur 3.11 ; résolution de
`requirements.txt` sur 3.11 et 3.12.
*Vérification* : les commandes du workflow exécutées dans un venv 3.11 neuf →
install OK, `ruff` OK, `pytest` 103 passed, `--dry-run` 0 erreur.
*Résultat* : **TERMINÉ côté code — le workflow n'a jamais tourné sur GitHub.**

---

**9. `8db0e4d` — Classification d'intention par le modèle**
*Fichiers* : `agents/orchestrator/orchestrator_agent.py`, `apps/backend/main.py`,
`tests/agents/test_orchestrator.py`
*Changement* : le modèle rapide choisit une étiquette parmi six. Réponse hors
liste ou modèle injoignable → repli sur les mots-clés, **journalisé**.
La classification est faite **une seule fois par requête**.
*Pourquoi* : « Explique-moi le **code** de la route » partait vers le `CoderAgent`.
*Vérification* : `pytest` → 123 passed ; mesuré via `POST /api/chat` avec un
fournisseur scripté → exactement **2 appels au modèle** (1 classification +
1 génération) là où le code en aurait fait 3.
*Résultat* : **TERMINÉ**

---

**10. `dc102ee` — BOM UTF-8**
*Fichiers* : 37 fichiers, `tests/test_encodage.py` (nouveau)
*Changement* : BOM retiré partout. L'audit en annonçait 3, il y en avait 37.
*Pourquoi* : le BOM rend la première ligne inutilisable comme texte. Un
`grep '^import'` ne voyait pas le premier import de dix modules — `httpx` et
`PyYAML` ont failli manquer dans `requirements.txt`.
*Vérification* : le garde-fou échoue quand un fichier avec BOM est ajouté et
passe une fois retiré ; `pytest` → 125 passed ; les 40 modules s'importent.
*Résultat* : **TERMINÉ**

---

### 26 août 2026 — T-02 · Contrôle des fichiers envoyés

**`/api/upload` filtre le type et la taille, et écrit par blocs**
*Fichiers* : `apps/backend/main.py`, `tests/test_upload.py` (nouveau),
`.env.example`, `docs/CHANGELOG.md`
*Changement* : liste blanche de 12 extensions audio/vidéo (415 sinon), plafond
réglable par `ARENA_UPLOAD_MAX_BYTES` (413 au-delà), écriture par blocs de 1 Mo,
suppression du fichier partiel en cas de refus, rejet du fichier vide.
*Pourquoi* : P-02. La route acceptait n'importe quel fichier et faisait
`buffer.write(await file.read())` — tout le fichier en mémoire avant le disque.
*Vérification* :
- `pytest tests/test_upload.py` → **23 passed**
- les mêmes 23 tests contre l'**ancien** code → **13 failed, 10 passed** : ils
  attrapent bien le défaut, ce ne sont pas des tests décoratifs
- mémoire mesurée sur un envoi de 64 Mo : pic **64,0 Mo** avant, **2,0 Mo** après
  (32×), et constant quelle que soit la taille du fichier
- suite complète → **148 passed, 17 deselected** ; `ruff check .` → 0 erreur
*Résultat* : **TERMINÉ**
*Décision* : la liste d'extensions reste dans le code, le plafond passe par
l'environnement — l'un est une règle métier (ARENA ne traite que du média),
l'autre dépend du disque de la machine. *Coût si c'est faux* : ajouter un format
demande une modification de code plutôt qu'un réglage.

---

### 26 août 2026 — T-06, T-07, T-08 · Documentation alignée sur le code

*Fichiers* : `docs/ROADMAP.md`, `docs/NEXT_STEPS.md`, `docs/CURRENT_TASK.md`,
`docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/START_HERE.md`,
`tests/test_documentation.py` (nouveau), `.dockerignore`
*Changement* :
- **T-06** — les trois affirmations fausses de la Phase 7 sont décochées et
  expliquées. Une Phase 7 bis liste ce qui a réellement été fait, avec le point
  encore ouvert. Une règle de tenue est posée en tête du fichier : *on ne coche
  qu'après avoir exécuté la vérification*.
- **T-07** — `NEXT_STEPS.md` décrivait encore la Phase 0 (« Créer README.md »).
  Il donne maintenant les trois prochaines étapes réelles.
- **T-08** — `RAPPORT_TRAVAIL.txt` supprimé de la racine (identique au md5 à la
  copie dans `docs/`). La ligne devenue redondante est retirée de `.dockerignore`.
- Hors périmètre nommé mais même défaut : `CURRENT_TASK.md` affirmait « 15
  défauts, **tous vérifiés par un test** ». Corrigé et daté.
- `DECISIONS.md` reçoit `DEC-0004` (le bac à sable refuse) et `DEC-0005`
  (licence propriétaire) — deux décisions prises et jamais consignées ici.
- `START_HERE.md` pointe vers ce carnet et rappelle de vérifier avant de croire.
*Pourquoi* : P-08. Une case cochée à tort est pire qu'une case vide — personne
ne revient sur un point déclaré clos.
*Vérification* :
- `tests/test_documentation.py` → **8 passed**. Les garde-fous couvrent : le
  retour d'une affirmation retirée, le doublon de rapport, un secret écrit en
  clair dans la documentation, et un chemin de fichier cité mais inexistant.
- test négatif : en réintroduisant les quatre défauts → **4 failed, 4 passed**,
  puis 8 passed après retour. Les garde-fous ne sont pas décoratifs.
- suite complète → **156 passed, 17 deselected** ; `ruff check .` → 0 erreur.
*Résultat* : **TERMINÉ**
*Décision* : rendre les affirmations de la documentation **testables** plutôt que
de se contenter de les corriger. *Coût si c'est faux* : le test ne connaît que
les quatre affirmations déjà prises en défaut ; il n'empêche pas d'en écrire une
nouvelle. Il empêche le retour de celles-ci, ce qui est déjà arrivé une fois.

---

### 26 août 2026 — T-01 · Purge des secrets : **préparée et vérifiée, non exécutée**

*Fichiers* : `scripts/preparer_purge_secrets.py` (nouveau),
`tests/test_preparer_purge_secrets.py` (nouveau),
`documents/RUNBOOK_PURGE_SECRETS.md` (nouveau)
*Changement* : rien dans l'historique du dépôt. La procédure est outillée,
documentée pas à pas, et prouvée sur des copies jetables.
*Pourquoi* : P-01. L'opération est irréversible et demande une décision du
propriétaire ; la rotation des clés ne peut être faite que par lui (les valeurs
vivent dans `.env`, jamais versionné).

**Trois découvertes qui contredisent les rapports d'audit :**

1. **Le dépôt a 44 commits, pas 1.** Les quatre rapports affirment « 1 commit »
   et en tirent la conclusion « aucune traçabilité ». C'est faux : l'historique
   remonte à `3466e2a feat: Commit initial ARENA v0.7.1`. Le clone d'audit était
   probablement superficiel (`--depth 1`).
   *Vérifié* : `git fetch --unshallow` puis `git rev-list --count --all` → 44.

2. **Il y a 6 secrets dans l'historique, pas 1.** Les rapports ne citent que la
   clé de `librechat.yaml`. L'historique contient aussi les valeurs de
   `CREDS_KEY`, `JWT_SECRET`, `JWT_REFRESH_SECRET`, `WEBUI_SECRET_KEY` et une
   clé LibreChat antérieure, toutes passées par `docker-compose.yml`.
   *Vérifié* : parcours de tous les blobs de l'historique.

3. **La commande proposée par les rapports détruirait le projet.**
   `git filter-repo --path librechat.yaml --invert-paths` supprime
   `librechat.yaml` de **tout** l'historique, version actuelle comprise — sans
   elle, LibreChat ne démarre plus. Et elle laisse les secrets des autres
   fichiers.
   *Vérifié* : exécutée sur une copie → `librechat.yaml : SUPPRIMÉ`, et le
   secret encore présent dans 2 commits.

**Ce qui a été vérifié sur copie, à la place :**
`git filter-repo --replace-text <fichier>` →
- les 44 commits sont conservés,
- `librechat.yaml`, `docker-compose.yml` et `main.py` sont intacts,
- les 6 secrets sortent de l'historique (`git log -S` → 0 commit pour chacun),
- `pytest` → 156 passed sur la copie purgée,
- `diff -r` entre le dépôt et la copie purgée → aucune différence dans les
  fichiers suivis.

**Outillage livré** : `scripts/preparer_purge_secrets.py` lit l'historique,
trouve les valeurs, les affiche **masquées**, et écrit le fichier de
remplacement **hors du dépôt** pour qu'il ne puisse pas être versionné.
15 tests le couvrent — dont un qui a trouvé un vrai défaut : un ancien
`docker-compose.yml` est encodé en latin-1 et faisait planter la lecture.

**Le runbook a été exécuté en entier sur une copie neuve, deux fois.**
Le premier passage a trouvé un défaut réel : `tests/test_preparer_purge_secrets.py`
contenait la vraie valeur de la clé, que la purge réécrivait — l'étape 5.3 du
runbook (`pytest`) échouait alors, et aurait laissé croire que la purge avait
cassé le projet. Les tests utilisent désormais des valeurs inventées.
Second passage, complet : 45 commits conservés, `librechat.yaml` intact,
**0 commit** pour chacun des 6 secrets, `pytest` → 171 passed.

*Résultat* : **PRÉPARÉ — en attente d'autorisation.** Marche à suivre :
`documents/RUNBOOK_PURGE_SECRETS.md`.
*Décision* : rédiger le fichier de remplacement hors du dépôt plutôt que dans un
`.gitignore`. *Coût si c'est faux* : une étape de plus pour l'utilisateur ; en
échange, aucune erreur de manipulation ne peut committer les secrets.

---

### 26 août 2026 — T-03 · Scan de secrets en CI

*Fichiers* : `.gitleaks.toml` (nouveau), `.github/workflows/ci.yml`,
`tests/test_gitleaks_config.py` (nouveau), `README.md`, `docs/CHANGELOG.md`
*Changement* : un troisième job CI télécharge `gitleaks` 8.28.0 (binaire épinglé,
pas l'action du marketplace qui exige une licence pour les organisations) et
lance deux contrôles — les fichiers actuels, puis les commits ajoutés par la
branche.
*Pourquoi* : la valeur d'une clé a été réintroduite **trois fois dans la même
journée**, chaque fois par inadvertance, chaque fois attrapée par un contrôle
automatique et jamais par une relecture.

**Le constat qui a décidé de la configuration** : les règles standard de
gitleaks **ne détectent pas** la clé de `librechat.yaml`. Elle est trop courte
pour leur seuil d'entropie. Autrement dit, `gitleaks` installé tel quel n'aurait
pas vu la fuite qui a déclenché l'audit.
*Vérifié* : même fichier piège, règles standard → code de sortie **0**
(rien détecté) ; règles d'ARENA → code **1**, `arena-librechat-apikey`.

Deux règles propres au projet ont donc été écrites, visant les emplacements où
ce projet écrit réellement des secrets : `apiKey:` dans un YAML, et les six
variables sensibles de `docker-compose.yml`.

*Vérifications, toutes exécutées :*
- fichiers actuels → **0 fuite** ; historique complet → **7 fuites**, soit les
  6 valeurs connues de P-01 (dont une présente dans deux fichiers)
- secret ajouté puis retiré dans deux commits de branche : étape 1 → code 0
  (le fichier est propre), étape 2 → code **1**, la CI échoue. C'est le cas
  qu'un scan de fichiers seul ne voit pas.
- 11 tests, dont 3 exécutant réellement `gitleaks`
- suite complète → **179 passed, 20 deselected** ; `ruff` → 0 erreur

**Un défaut trouvé pendant la mise au point** : les motifs de la liste
d'exclusion étaient ancrés par `^`. Avec `--source /chemin/absolu`, ils cessent
silencieusement de s'appliquer et 3 faux positifs apparaissent — la CI aurait pu
échouer sans raison. Les motifs sont désormais en `(^|/)`, et un test refuse
tout motif ancré.

**Limite connue, assumée** : ces règles détectent un secret dans sa *forme
structurée* (`apiKey: "..."`, `CREDS_KEY=...`). Une clé recopiée en pleine
prose dans un document n'est pas attrapée par gitleaks. C'est
`tests/test_documentation.py` qui couvre ce cas — les deux sont complémentaires,
aucun ne suffit seul.

*Résultat* : **TERMINÉ**
*Décision* : deux contrôles (fichiers + commits de la branche) plutôt qu'un scan
de l'historique complet. *Coût si c'est faux* : les 7 fuites déjà présentes dans
l'historique ne font pas échouer la CI — sinon elle serait rouge en permanence
jusqu'à T-01. Une fois T-01 exécutée, le scan complet pourra être activé.

---

### 26 août 2026 — T-04, T-05 · Limitation de débit et journalisation des refus

*Fichiers* : `apps/backend/rate_limit.py` (nouveau), `apps/backend/main.py`,
`tests/test_rate_limit.py` (nouveau), `.env.example`, `docs/CHANGELOG.md`
*Changement* :
- **T-04** — fenêtre glissante en mémoire, 10 requêtes par minute et par adresse
  (réglable). Appliquée aux quatre routes qui appellent le modèle :
  `/v1/chat/completions`, `/api/chat`, `/api/chat/stream`, `/api/process-video`.
  Réponse 429 avec un en-tête `Retry-After`.
- **T-05** — chaque refus d'authentification est journalisé avec l'adresse, la
  route et le motif (clé absente / clé invalide).
*Pourquoi* : un appel à Ollama occupe la carte graphique plusieurs secondes.
Sans plafond, une page qui rafraîchit en boucle sature la machine. Et sans
journal, une tentative répétée d'accès ne laisse aucune trace.

*Vérifications, toutes exécutées :*
- `pytest tests/test_rate_limit.py` → **20 passed**
- test négatif, limitation retirée → **3 failed** ; journalisation retirée →
  **1 failed** ; puis 20 passed après remise en état
- suite complète → **199 passed, 20 deselected** ; `ruff` → 0 erreur ;
  `gitleaks` → 0 fuite
- non-régression : un message de chat coûte toujours **2 appels au modèle**

*Décisions :*
1. **Écrire le limiteur plutôt qu'ajouter `slowapi`** — une fenêtre glissante
   tient en 80 lignes et le projet évite une dépendance de plus. *Coût si c'est
   faux* : le compteur vit en mémoire d'un seul processus ; un déploiement
   multi-processus le rendrait inexact. C'est écrit dans le module.
2. **Une requête refusée n'est pas comptabilisée** — sinon un client bloqué se
   re-pénaliserait à chaque tentative et ne sortirait jamais de la fenêtre.
   *Coût si c'est faux* : un client insistant n'est pas pénalisé davantage.
3. **L'authentification passe avant la limitation** — une requête sans clé ne
   consomme pas le quota du client. *Coût si c'est faux* : une attaque non
   authentifiée ne peut pas épuiser le quota d'un utilisateur légitime, mais
   elle n'est pas ralentie non plus. Un test couvre ce choix.
4. **La clé présentée n'est jamais journalisée.** Un journal qui contient des
   secrets est un secret de plus à protéger. Un test le vérifie.

*Résultat* : **TERMINÉ**

---

### 26 août 2026 — T-12 phase 1/3 · Lecture d'une source web

*Fichiers* : `tools/search/source_fetcher.py` (nouveau),
`tests/tools/test_source_fetcher.py` (nouveau)
*Changement* : `SourceFetcher` télécharge une page et en extrait le texte
lisible. C'est l'étape « lire la source » du pipeline d'information fraîche ;
elle ne dépend d'aucun modèle et se teste seule.
*Pourquoi* : T-12. Le chat n'a aujourd'hui aucun moyen d'aller vérifier quoi que
ce soit sur le web ; `WebSearchTool` ne renvoie que des résumés de moteur de
recherche, jamais le contenu des pages.

**Trois règles portées par l'outil :**
1. Une page inaccessible **est signalée** (`REFUSED` / `FAILED`), jamais
   remplacée par un texte plausible.
2. Une **adresse interne est refusée**. Les URL viennent d'un moteur de
   recherche, donc de l'extérieur : sans ce garde-fou, ARENA pourrait être
   amené à lire ses propres services (`127.0.0.1:8000`) et à en restituer le
   contenu dans une réponse.
3. Taille, durée et longueur de texte **plafonnées**, et la troncature est
   déclarée dans le résultat.

*Vérifications, toutes exécutées :*
- `pytest tests/tools/test_source_fetcher.py` → **24 passed**, sans aucun accès
  réseau : les réponses HTTP passent par un transport simulé, donc le vrai code
  de `fetch()` est parcouru de bout en bout.
- garde-fou éprouvé contre un **vrai serveur local** : le lecteur normal renvoie
  `REFUSED` et un texte vide ; le même lecteur, garde-fou désactivé, lit bien la
  page — ce qui prouve que le refus vient du contrôle et non d'un serveur muet.
- suite complète → **223 passed, 20 deselected** ; `ruff` → 0 ; `gitleaks` → 0.

*Décision* : extraire le texte avec `html.parser` de la bibliothèque standard
plutôt que d'ajouter `beautifulsoup4` en dépendance directe. *Coût si c'est
faux* : l'extraction est un peu moins bonne sur les pages très mal formées ;
`requirements.txt` reste à 12 dépendances.

*Résultat* : **TERMINÉ** — phase 1 sur 3.

---

### 26 août 2026 — T-12 phase 2/3 · Agent d'information fraîche

*Fichiers* : `agents/fresh_info/fresh_info_agent.py` (nouveau),
`tests/agents/test_fresh_info.py` (nouveau)
*Changement* : `FreshInfoAgent` enchaîne recherche → lecture des pages →
répartition d'un budget de contexte → synthèse **avec sources numérotées**.
Le modèle reçoit le **texte réel des pages**, plus jamais les seuls résumés du
moteur de recherche.

**Deux refus explicites, et c'est le cœur de la conception :**
- aucun résultat de recherche → **le modèle n'est pas appelé** ;
- aucune page lisible → **le modèle n'est pas appelé non plus**, et l'agent
  rapporte ce qu'il a tenté de lire et pourquoi cela a échoué.

Une réponse inventée coûte plus cher qu'une absence de réponse : sans source,
l'agent le dit au lieu de répondre de mémoire.

**Contrainte matérielle traitée explicitement** : `num_ctx` vaut 4096 jetons.
Envoyer trois pages entières ferait déborder le contexte et noierait la question.
Un budget de 8000 caractères est réparti entre les sources retenues, et la
troncature est déclarée source par source.

*Vérifications, toutes exécutées :*
- `pytest tests/agents/test_fresh_info.py` → **15 passed**
- chaîne complète contre un **vrai serveur HTTP** (recherche doublée, lecture
  réelle, modèle simulé) : 3 pages proposées → 1 lue, 1 en `code HTTP 404`,
  1 en `type non lisible : application/pdf`. Le prompt envoyé contient le texte
  réel de la page, les entités HTML décodées, aucun script, et pèse
  **612 caractères**.
- suite complète → **238 passed, 20 deselected** ; `ruff` → 0 ; `gitleaks` → 0.

*Deux défauts trouvés par les tests eux-mêmes* : une aide de test confondait
« titre absent » et « titre par défaut », et un test comptait le caractère `x`
comme remplissage alors qu'il apparaît dans `exemple.test` — le budget semblait
dépassé de 4 caractères.

*Décision* : lire les pages en parallèle (`asyncio.gather`). *Coût si c'est
faux* : plusieurs requêtes réseau simultanées vers des sites différents ; le GPU
n'est pas concerné, l'attente est réseau.

*Résultat* : **TERMINÉ** — phase 2 sur 3. L'agent n'est pas encore branché sur
le routeur : c'est la phase 3.

---

### 26 août 2026 — T-12 phase 3/3 · Le routeur appelle l'agent · **T-12 TERMINÉE**

*Fichiers* : `agents/orchestrator/orchestrator_agent.py`, `apps/backend/main.py`,
`tests/test_fresh_info_routing.py` (nouveau), `tests/agents/test_orchestrator.py`
*Changement* : nouvelle intention `FRESH_INFO` dans la liste fermée du routeur,
décrite dans le prompt de classification et reconnue par le repli mots-clés.
`dispatch_request` l'envoie à `FreshInfoAgent`. `/api/chat` renvoie les sources
dans un champ dédié ; la passerelle `/v1`, qui n'a pas de champ pour cela, les
liste sous la réponse. Un modèle `arena-fresh` apparaît dans le menu des
interfaces.

*Vérifications, toutes exécutées :*
- `pytest tests/test_fresh_info_routing.py` → **11 passed**
- chaîne complète depuis une requête HTTP, avec un **vrai serveur web** comme
  source : `POST /api/chat` → intention `FRESH_INFO`, agent `FreshInfoAgent`,
  réponse citant `[1]`, source `http://127.0.0.1:.../py`. **2 appels au modèle**
  (1 classification + 1 synthèse), pas un de plus.
  `POST /v1/chat/completions` avec `arena-fresh` → réponse suivie d'un bloc
  `**Sources**`.
- suite complète → **258 passed, 20 deselected** ; `ruff` → 0 ; `gitleaks` → 0

**Un défaut préexistant trouvé par cette vérification** : `/api/chat` annonçait
`intent: "CHAT"` même quand un agent spécialisé avait répondu — le champ n'était
jamais renseigné hors conversation. Vrai pour les six intentions, pas seulement
la nouvelle. Corrigé dans `dispatch_request`, avec un test.

*Décision* : citer les sources **dans le texte** pour la passerelle `/v1`. Le
format OpenAI n'a pas de champ pour cela, et sans elles le lecteur ne saurait
pas d'où vient la réponse. *Coût si c'est faux* : la réponse est un peu plus
longue dans LibreChat ; `/api/chat` garde les sources en données structurées.

*Résultat* : **T-12 TERMINÉE** — 3 phases sur 3.

**Ce que T-12 ne fait pas, et qui reste ouvert :**
- Le prompt système contient toujours des faits datés écrits en dur
  (« Année actuelle : 2026 », le président du Sénégal). C'est **T-13**, et une
  question portant dessus part maintenant sur le web — mais la conversation
  ordinaire lit encore ces lignes.
- Aucun classement des sources par fiabilité : les trois premiers résultats du
  moteur sont lus, dans l'ordre.
- Aucune vérification croisée des réponses (T-14, T-18).

---

### 26 août 2026 — T-13 · Retrait des faits figés du prompt système

*Fichiers* : `apps/backend/main.py`, `tests/test_system_prompt.py` (nouveau)
*Changement* : `get_arena_system_prompt()` n'écrit plus aucun fait daté en dur.
Disparaissent : « Année actuelle : 2026 », le président et le premier ministre
du Sénégal — trois valeurs figées dans le code.

*Ce qui remplace :*
- la **date réellement lue sur la machine** (`date.today()`, isolée dans
  `date_du_jour()` pour être testable) ;
- une consigne explicite : connaître la date ne donne aucune connaissance des
  événements récents, donc ne pas répondre de mémoire sur ce qui a pu changer ;
- les faits que le propriétaire a **lui-même enregistrés** en mémoire longue,
  avec la réserve qu'ils ont pu changer. Un fait absent n'apparaît pas : rien
  n'est inventé pour combler.

*Pourquoi* : P-03. Une valeur figée devient fausse sans que rien ne le signale,
et le modèle la répète avec l'assurance d'un fait vérifié. Le retrait n'était
possible qu'après T-12 : sans le pipeline web, retirer ces lignes aurait laissé
le modèle deviner. Désormais, la question part vérifier.

*Vérifications, toutes exécutées :*
- `pytest tests/test_system_prompt.py` → **13 passed**
- test négatif, ancienne version restaurée → **9 failed, 4 passed**, puis
  13 passed après retour
- la date est prouvée **calculée et non écrite** : horloge fixée au 15/03/2030 →
  le prompt affiche `15/03/2030` et ne contient plus « 2026 »
- un garde-fou porte aussi sur le **fichier source** : les retirer du prompt sans
  les retirer du code laisserait le piège en place
- suite complète → **271 passed, 20 deselected** ; `ruff` → 0 ; `gitleaks` → 0
- non-régression T-12 : la chaîne complète répond toujours `FRESH_INFO` /
  `FreshInfoAgent` en 2 appels au modèle

*Décision* : injecter la date réelle plutôt qu'aucune date. Le prompt de
référence interdit de **régler le problème de fraîcheur** en écrivant une date —
c'est fait, T-12 s'en charge. La date lue sur la machine est une mesure, pas une
affirmation, et elle aide le modèle à situer « l'an dernier ». *Coût si c'est
faux* : le modèle pourrait prendre la date pour une autorisation d'affirmer des
faits récents ; les trois lignes de consigne qui la suivent existent pour ça.

*Résultat* : **TERMINÉ** — P-03 est clos pour sa partie « faits figés ».

---

### 26 août 2026 — T-19 phase 1/3 · Filet de sécurité, configuration, objets partagés

*Fichiers* : `tests/test_surface_api.py` (nouveau), `apps/backend/config.py`
(nouveau), `apps/backend/runtime.py` (nouveau), `apps/backend/__init__.py`,
`apps/backend/main.py`
*Changement* : rien dans le comportement. `main.py` passe de **652 à 588 lignes** ;
les réglages lus dans l'environnement vont dans `config.py`, les objets créés une
fois (mémoire, permissions, modèles, 13 agents) dans `runtime.py`.

**Le filet de sécurité d'abord, l'extraction ensuite.** `test_surface_api.py`
fige la surface HTTP : la liste des routes, leurs méthodes, et **les dépendances
attachées à chacune** — c'est là que vivent l'authentification et la limitation
de débit. Deux tests transversaux valent leur place : aucune route `/api` ou
`/v1` sans `verify_api_key`, aucune route appelant le modèle sans
`limiter_debit`. Un remaniement qui les casse a changé le comportement, pas
seulement l'organisation.

**Un défaut introduit puis corrigé dans la même phase.** `runtime.py` importe les
agents ; sans la racine du dépôt dans `sys.path`, cet import échoue. Cela
fonctionnait par chance — `apps.backend.config`, qui préparait le chemin, se
trie avant `apps.backend.runtime` par ordre alphabétique. Une garantie qui tient
à un nom de fichier n'en est pas une. La préparation du chemin est passée dans
`apps/backend/__init__.py`, que Python exécute avant tout module du paquet.

*Vérifications, toutes exécutées :*
- `pytest tests/test_surface_api.py` → **18 passed** (empreinte inchangée)
- suite complète → **289 passed, 20 deselected** ; `ruff` → 0 ; `gitleaks` → 0
- import depuis `/tmp`, racine retirée de `sys.path` au départ → OK, 13 routes
- chaînes de bout en bout inchangées : T-12 répond toujours `FRESH_INFO` /
  `FreshInfoAgent`, un message de chat coûte toujours 2 appels au modèle

*Décision* : garder les fonctions dans `main.py` pour cette phase, et n'y importer
que des noms. Les tests remplacent `main.ARENA_API_KEY`, `main.fresh_agent`,
`main.memory` : tant que les fonctions lisent les variables globales de `main`,
ces remplacements continuent de fonctionner. *Coût si c'est faux* : la phase
suivante, qui déplace les fonctions, devra mettre à jour ces tests — et c'est
tant mieux, un test qui remplace le mauvais module passerait pour de mauvaises
raisons.

*Résultat* : **TERMINÉ** — phase 1 sur 3.

---

### 26 août 2026 — T-19 phase 2/3 · Sécurité et instruction système extraites

*Fichiers* : `apps/backend/security.py` (nouveau), `apps/backend/prompts.py`
(nouveau), `apps/backend/main.py`, 5 fichiers de tests
*Changement* : `main.py` passe de **588 à 470 lignes**. Les trois contrôles qui
décident si une requête va plus loin — authentification, débit, chemin de
fichier — vivent maintenant dans un fichier de 83 lignes qu'on lit d'un seul
coup d'œil. L'instruction système est dans un fichier de 65 lignes, où la règle
« aucun fait daté écrit en dur » est vérifiable sans être noyée.

**Le piège de cette phase, et ce qui le referme.** Les tests remplaçaient
`main.ARENA_API_KEY`. Une fois `verify_api_key` déplacée, elle lit la variable de
`security` : le remplacement dans `main` n'a plus aucun effet — et un test qui
remplace le mauvais module **passe sans rien vérifier**. Cinq fichiers de tests
ont été redirigés vers le module propriétaire, et un test neuf
(`test_aucun_reglage_n_est_duplique_dans_main`) refuse désormais qu'une copie de
ces réglages réapparaisse dans `main`.

Il a mordu immédiatement : trois de mes scripts de non-régression réglaient
`main.ARENA_API_KEY` et mesuraient **0 appel au modèle** au lieu de 2 — la requête
était refusée avant d'atteindre l'agent. Corrigés.

**Le test d'inventaire a changé de forme.** Il affirmait « tout reste accessible
depuis `main` », ce que le découpage invalide volontairement. Il affirme
maintenant l'invariant qui compte : chaque nom a un module propriétaire et s'y
trouve toujours — 58 noms répartis sur 5 modules.

*Vérifications, toutes exécutées :*
- `pytest tests/test_surface_api.py` → **21 passed**, empreinte des routes et de
  leurs dépendances inchangée
- suite complète → **292 passed, 20 deselected** ; `ruff` → 0 ; `gitleaks` → 0
- chaînes de bout en bout, après correction des scripts : T-12 répond
  `FRESH_INFO` / `FreshInfoAgent`, 2 appels au modèle, refus SSRF tenu, mémoire
  d'envoi toujours à 2 Mo pour 64 Mo

*Résultat* : **TERMINÉ** — phase 2 sur 3.

---

### 26 août 2026 — T-19 phase 3/3 · Routeurs séparés · **T-19 TERMINÉE**

*Fichiers* : `apps/backend/routers/{chat,media,openai_gateway}.py` (nouveaux),
`apps/backend/main.py`, 5 fichiers de tests
*Changement* : `main.py` passe de 470 à **61 lignes**. Il n'assemble plus que
l'application, les origines autorisées, le dossier des rendus, `/` et `/health`,
puis inclut trois routeurs.

**Résultat du découpage, mesuré :**

| Fichier | Rôle | Lignes |
|---|---|---|
| `main.py` | assemblage | **61** |
| `config.py` | réglages lus dans l'environnement | 61 |
| `runtime.py` | objets partagés | 58 |
| `security.py` | authentification, débit, chemins | 83 |
| `prompts.py` | instruction système | 65 |
| `apps/backend/routers/chat.py` | conversation et aiguillage | 149 |
| `apps/backend/routers/media.py` | envoi et chaîne vidéo | 158 |
| `apps/backend/routers/openai_gateway.py` | passerelle `/v1` | 174 |

Le critère de T-19 (« aucun fichier > 250 lignes ») est tenu : le plus gros
fichier du projet est `tools/search/source_fetcher.py`, à 220 lignes.

**Un piège du filet de sécurité lui-même.** Cette version de FastAPI ne met pas
les routes incluses à plat dans `app.routes` : elle conserve un objet
intermédiaire. Le test de surface ne voyait donc **plus aucune route métier** et
serait passé à vide sur les contrôles transversaux. Le parcours est désormais
récursif, et j'ai vérifié à la main qu'il voit bien les 8 routes avec leurs
dépendances — un test vert après remaniement doit prouver qu'il a regardé.

**Une conséquence assumée du découpage** : `fresh_agent` est importé par deux
modules (`chat` et `openai_gateway`). En production c'est le même objet — un test
l'affirme. Dans un test, le remplacer demande de viser les deux. Mon script de
non-régression ne visait qu'un seul, et la passerelle `/v1` est tombée sur le
vrai agent : sans moteur de recherche installé, il a répondu *« Aucun résultat…
je préfère le dire plutôt que répondre de mémoire »*. Le refus a fonctionné
exactement comme conçu.

*Vérifications, toutes exécutées :*
- `tests/test_surface_api.py` → **21 passed**, et vérification manuelle : 8 routes
  vues, `verify_api_key` sur les 6 routes métier, `limiter_debit` sur les 4 qui
  appellent le modèle
- suite complète → **295 passed, 20 deselected** ; `ruff` → 0 ; `gitleaks` → 0
- chaînes de bout en bout : `/api/chat` et `/v1` répondent `FRESH_INFO` /
  `FreshInfoAgent` avec sources, 2 appels au modèle ; refus SSRF tenu ; envoi de
  64 Mo toujours à 2 Mo de pic

*Décision* : `formater_sources` et `dispatch_request` restent dans
`apps/backend/routers/chat.py`, importés par la passerelle. *Coût si c'est faux* : la
passerelle dépend du routeur de chat ; l'inverse aurait demandé un module de plus
pour deux fonctions.

*Résultat* : **T-19 TERMINÉE** — 3 phases sur 3, comportement inchangé.

---

### 26 août 2026 — Indexation documentaire, phase 1/3 · Lecture d'un document

*Fichiers* : `tools/documents/reader.py` (nouveau),
`tests/tools/test_document_reader.py` (nouveau), `requirements.txt`,
`.github/workflows/ci.yml`
*Changement* : ARENA sait ouvrir un PDF, un `.docx`, un `.txt`, un `.md` et un
`.csv`, et en extraire le texte avec sa provenance.

**Le constat de départ** : `LightRAGTool.insert_text()` et
`GraphRAGTool.add_document()` n'acceptent que du **texte brut**. Aucun des deux
ne sait ouvrir un PDF. L'indexation documentaire était donc annoncée comme
« outils branchés » alors que la première étape — lire le document — n'existait
pas.

**Deux règles portées par le module :**
1. Un document illisible est **signalé** : `VIDE` (PDF scanné), `NON_PRIS_EN_CHARGE`
   (format inconnu), `ECHEC` (absent, corrompu, trop gros). Jamais un texte
   plausible à la place d'un texte réel.
2. Chaque passage garde son origine — fichier, et **numéro de page** pour un PDF.
   Sans elle, une réponse documentaire ne vaut pas mieux qu'une réponse de
   mémoire.

Le contenu des **tableaux Word** est extrait : un devis y vit souvent, et
l'ignorer viderait le document de l'essentiel.

*Vérifications, toutes exécutées :*
- `pytest tests/tools/test_document_reader.py` → **20 passed**. Les fichiers
  d'essai sont de **vrais** PDF et `.docx` fabriqués dans le test — un lecteur de
  PDF vérifié sur une chaîne de caractères ne prouve rien. Le PDF est construit à
  la main (objets, flux, xref), sans dépendance d'écriture.
- suite complète → **315 passed, 20 deselected** (code de sortie 0, sans tube)
- `ruff` → 0 ; `gitleaks` → 0 ; chaîne T-12 → 0 ; refus SSRF → 0
- les commandes exactes de la CI rejouées dans un venv 3.11 neuf → install OK,
  ruff OK, pytest 315 passed

*Décision* : déclarer `pypdf` et `python-docx` en dépendances directes plutôt que
d'écrire un lecteur de PDF. *Coût si c'est faux* : deux paquets de plus dans
`requirements.txt` (12 → 14) ; ils étaient déjà présents en transitif, et écrire
un extracteur de PDF à la main serait une mauvaise idée.

*Résultat* : **TERMINÉ** — phase 1 sur 3.

**Ce qui reste, et une limite à connaître :** la phase 3 (indexation réelle)
**ne sera pas vérifiable sur la machine de développement** : LightRAG exige
Ollama et un modèle d'embeddings, GraphRAG exige Docker. Le refus en leur absence
sera vérifié ici ; l'indexation elle-même devra l'être chez le propriétaire.

---

### 26 août 2026 — Indexation documentaire, phase 2/3 · Le classeur

*Fichiers* : `tools/documents/inventory.py` (nouveau),
`tests/tools/test_document_inventory.py` (nouveau), `tests/test_gitleaks_config.py`,
`.gitignore`, `README.md`
*Changement* : un dossier `data/documents/` où le propriétaire dépose ses
fichiers, et un inventaire qui répond à quatre questions : quels documents sont
nouveaux, lesquels ont changé, lesquels sont inchangés, lesquels ont disparu.

**Pourquoi un inventaire.** Indexer un passage occupe la carte graphique le temps
d'en calculer le vecteur. Refaire ce travail sur un fichier qui n'a pas bougé,
c'est occuper le GPU pour rien — sur une RTX A2000 partagée avec le modèle de
conversation, cela se voit.

**Trois choix qui portent la conception :**
1. Le suivi porte sur le **contenu** (empreinte SHA-256), pas sur la date de
   modification. Recopier un fichier change sa date sans changer ce qu'il dit.
2. Un document **disparu est signalé**, jamais retiré en silence : l'index
   continuerait sinon à répondre à partir d'un fichier supprimé.
3. Un inventaire illisible est **reconstruit**, pas fatal. Le pire cas doit être
   « tout réindexer une fois », jamais « ne plus rien pouvoir indexer ».

**Le point de confidentialité, et il compte.** Le dépôt est public. `.gitignore`
exclut désormais `data/documents/` et `data/rag/`, et trois tests vérifient qu'un
devis ou une facture **ne peut pas** être versionné. L'inventaire lui-même ne
contient aucun contenu de document — seulement nom, empreinte, date, compteurs :
il est écrit sur le disque, y recopier une facture serait une fuite. Un test
l'affirme sur un fichier contenant un montant et un RIB.

*Vérifications, toutes exécutées :*
- `pytest tests/tools/test_document_inventory.py` → **19 passed**
- classeur réel (2 pages de PDF, un Word avec tableau, un Markdown, un `.jpg` et
  un `.xlsx`) :
  - 1er passage → 3 nouveaux, 2 ignorés, tous lus avec leur provenance
    (`devis_2026_041.pdf, page 2`)
  - 2e passage → **0 à faire**, 3 inchangés
  - 3e passage, un devis corrigé et une note supprimée → 1 modifié, 1 disparu,
    1 inchangé
  - l'inventaire écrit ne contient ni le montant ni le nom du chantier
- suite complète → **338 passed, 20 deselected** (code de sortie 0, sans tube) ;
  `ruff` → 0 ; `gitleaks` → 0 ; chaîne T-12 → 0

*Résultat* : **TERMINÉ** — phase 2 sur 3.

---

### 26 août 2026 — Indexation documentaire, phase 3/3 · La commande · **TERMINÉE**

*Fichiers* : `tools/documents/indexer.py` (nouveau),
`scripts/indexer_documents.py` (nouveau),
`tests/tools/test_document_indexer.py` (nouveau), `README.md`
*Changement* : la chaîne est branchée — inventaire → lecture → insertion dans
LightRAG → inventaire mis à jour. Une commande unique :
`python scripts/indexer_documents.py`.

**Trois règles, une seule idée** : un index qui se croit à jour alors qu'il ne
l'est pas est pire qu'un index vide.
1. Le moteur est **vérifié avant de commencer**. Ollama muet ou
   `nomic-embed-text` absent → refus, rien d'indexé, rien de noté.
2. Un document n'est noté comme indexé **que s'il l'a vraiment été**. Une
   insertion refusée le laisse hors de l'inventaire ; il est repris au passage
   suivant.
3. La **provenance part avec le texte** : chaque passage est inséré préfixé de
   `[Source : devis.pdf, page 2]`. Sans cela, tout le travail de lecture page par
   page serait perdu à l'insertion.

*Vérifications, toutes exécutées :*
- `pytest tests/tools/test_document_indexer.py` → **18 passed**
- **la vraie commande, sur cette machine, Ollama réellement absent** :
  `Indexation refusee. Ollama ne repond pas sur http://127.0.0.1:11434
  (ConnectError). Demarre-le avec : ollama serve` — code de sortie 1, et
  **aucun inventaire créé**
- chaîne complète contre un **faux Ollama** répondant comme le vrai : modèle
  d'embeddings retiré → message `ollama pull nomic-embed-text` ; puis 2 documents
  indexés, 1 ignoré, le texte envoyé au moteur portant bien
  `[Source : devis.pdf, page 1]` et `page 2` ; relance → *rien à faire* ;
  l'inventaire écrit ne contient ni le montant ni le nom du chantier
- suite complète → **356 passed, 20 deselected** (code 0, sans tube) ; `ruff` → 0 ;
  `gitleaks` → 0 ; chaîne T-12 → 0 ; classeur → 0

*Décision* : `indexer_documents` prend le moteur en argument plutôt que de
l'instancier. *Coût si c'est faux* : la commande doit le construire elle-même ;
en échange, toute la chaîne est testable sans GPU — 18 tests contre 0 sinon.

*Résultat* : **INDEXATION DOCUMENTAIRE TERMINÉE** — 3 phases sur 3.

**Ce qui n'a pas pu être vérifié ici, et qui reste à faire chez le
propriétaire** : l'insertion réelle dans LightRAG et la qualité des réponses.
Cette machine n'a ni GPU, ni Ollama, ni modèle d'embeddings. Tout le code de la
commande a été exécuté ; seul le moteur documentaire était doublé.
**À faire côté propriétaire** : déposer des documents dans `data/documents/`,
lancer `ollama pull nomic-embed-text`, puis
`python scripts/indexer_documents.py`, et consigner le résultat ici.

---

### 26 août 2026 — Interface hors ligne

*Fichiers* : `apps/frontend/index.html`, `apps/frontend/vendor/tailwind.js`
(nouveau), `apps/frontend/vendor/PROVENANCE.md` (nouveau),
`apps/backend/main.py`, `tests/test_frontend.py` (nouveau)
*Changement* : la mise en forme est servie par le backend sur `/static/` au lieu
d'être chargée depuis `cdn.tailwindcss.com`.
*Pourquoi* : P-09. Le projet se revendique local-first (`DEC-0002`) et son
interface ne fonctionnait pas sans connexion.

*Vérifications, toutes exécutées :*
- **Rendu dans un vrai Chromium, toute requête sortante bloquée.**
  Avant : `['https://cdn.tailwindcss.com/']` bloquée, en-tête **137,875 px**,
  corps en `block`, `window.tailwind` absent — l'interface était bien cassée.
  Après : **aucune** requête sortante, en-tête **64 px** (la classe `h-16`
  s'applique), corps en `flex column`, `window.tailwind` présent.
- `pytest tests/test_frontend.py` → **8 passed** hors ligne, **1 passed** avec le
  navigateur (marqué `integration`)
- suite complète → **364 passed, 21 deselected** ; `ruff` → 0 ; `gitleaks` → 0
  (le fichier de 407 Ko ne déclenche aucun faux positif)

*Décision* : embarquer le fichier du CDN plutôt que compiler Tailwind. *Coût si
c'est faux* : 407 Ko dans le dépôt, et la mise en forme est calculée dans le
navigateur au chargement plutôt qu'à la compilation. En échange, le projet
n'acquiert pas de chaîne Node pour un seul fichier. `PROVENANCE.md` déclare
l'origine, la version, la date, la taille et l'empreinte ; deux tests refusent
que le fichier présent diverge de ce qui est déclaré — sans quoi la provenance
ne prouverait rien.

*Résultat* : **TERMINÉ** — P-09 est clos.

---

### 26 août 2026 — CI rouge sur la PR #1 : un test qui affirmait un état temporaire

*Fichiers* : `scripts/preparer_purge_secrets.py`,
`tests/test_preparer_purge_secrets.py`
*Symptôme* : `Lint and offline test suite` en échec sur la PR #1 —
`test_le_script_lit_l_historique_reel_du_depot` :
`attendu au moins 5 secrets, trouvé 0`.

**Cause racine.** Le test interrogeait l'historique Git de **ce dépôt** et
exigeait d'y trouver au moins 5 secrets. En intégration continue,
`actions/checkout` fait un clone d'un seul commit : `git log --all` ne voit rien.
Reproduit à l'identique en local avec `git clone --depth 1` → 1 failed.

**Le défaut est plus profond qu'un réglage de CI.** Ce test affirmait un état
**temporaire** du dépôt — « il contient des secrets ». Une fois la purge (T-01)
faite, il aurait échoué une seconde fois, pour la raison inverse. Augmenter
`fetch-depth` l'aurait fait passer aujourd'hui et casser demain.

**Correctif.** Le dépôt interrogé devient un paramètre. Cinq tests neufs
fabriquent de **vrais dépôts Git** (`git init`, commits successifs) et vérifient
le comportement sur des cas maîtrisés : une clé versionnée puis retirée est
retrouvée, une référence `${VAR}` ne l'est pas, **un dépôt sans secret ne renvoie
rien** — l'état attendu après la purge. Le test sur le dépôt réel subsiste mais
n'affirme plus de compte : seulement qu'il s'exécute et ne renvoie que des
valeurs de forme secrète.

**Trouvé au passage** : sur un clone superficiel, le script annonçait « aucun
secret trouvé, rien à purger ». Un mensonge tranquille. Il détecte désormais
`.git/shallow`, refuse de conclure et indique `git fetch --unshallow`.

*Vérifications, toutes exécutées :*
- échec reproduit avant correction (`--depth 1` → 1 failed), puis
  **369 passed** dans le même clone superficiel
- historique complet → **369 passed**, `ruff` → 0, `gitleaks` → 0
- le script sur clone superficiel → avertit, code de sortie 1 ; sur historique
  complet → 6 secrets trouvés, comme avant

*Décision* : rendre le dépôt injectable plutôt qu'augmenter `fetch-depth` en CI.
*Coût si c'est faux* : le test ne parcourt plus l'historique réel du projet ; en
échange il reste vrai avant **et** après la purge, et ne dépend plus de la
profondeur du clone.

---

## IN PROGRESS

**Tâche courante** : PR #1 ouverte sur `master`. CI remise au vert après un
test qui dépendait de la profondeur du clone.
**État exact** : deux actions restent, et elles n'appartiennent qu'au
propriétaire — changer les cinq clés dans `.env`, et autoriser la réécriture de
l'historique (irréversible, casse les clones existants).
**Prochaine action concrète, et elle appartient au propriétaire** : déposer
des documents dans `data/documents/`, `ollama pull nomic-embed-text`, puis
`python scripts/indexer_documents.py`. Reste également dû : l'étape 1 de
`RUNBOOK_PURGE_SECRETS.md` (rotation des cinq clés).

---

## PENDING

Par priorité. Effort = estimation, à confirmer.

### Priorité 1 — Sécurité non close

| # | Tâche | Effort | Critère de validation |
|---|---|---|---|
| T-01 | Purger la clé de l'historique Git + rotation | 20 min | `git log -S "<ancienne clé>"` ne renvoie rien |

### Priorité 2 — Alignement documentation ↔ code

**Terminé le 26/08/2026** (T-06, T-07, T-08). Les affirmations corrigées sont
désormais protégées par `tests/test_documentation.py`.

### Priorité 3 — Performance et matériel

| # | Tâche | Effort | Critère de validation |
|---|---|---|---|
| T-09 | Vérifier l'existence du tag `qwen3.5:9b` | 5 min | `ollama list` le montre, ou le nom est corrigé |
| T-10 | Arbitrer le budget VRAM : un seul modèle chaud | 1 h | VRAM mesurée < 12 Go, temps de bascule mesuré |
| T-11 | Mesurer et consigner les temps de réponse de référence | 45 min | Section *PERFORMANCE* remplie de vrais chiffres |

### Priorité 4 — Capacités (roadmap du prompt de référence)

**T-12 terminée le 26/08/2026** — voir *COMPLETED*.

| # | Tâche | Effort | Critère de validation |
|---|---|---|---|
| T-14 | Routeur enrichi : besoin de fraîcheur, de RAG, d'outils, de vérification | 3 h | Le routeur renvoie une décision structurée, testée |
| T-15 | Passerelle de modèles par capacité (`fast_chat`, `coding`, `reasoning`…) | 3 h | Un agent demande une capacité, pas un nom de modèle |
| T-16 | Mémoire sémantique et mémoire utilisateur séparées | 4 h | Une information ancienne pertinente est retrouvée par similarité |
| T-18 | Progression visible pendant les opérations longues | 2 h | L'interface affiche « recherche », « lecture », « génération » |

### Priorité 5 — Dette technique

**T-19 terminée le 26/08/2026** — voir *COMPLETED*.

| # | Tâche | Effort | Critère de validation |
|---|---|---|---|
| T-20 | Tailwind servi en local (le CDN contredit le local-first) | 20 min | Interface stylée sans connexion réseau |
| T-21 | Accès SQLite non bloquant depuis les routes `async` | 2 h | Charge concurrente sans blocage mesuré |
| T-22 | Retirer les emojis des 4 lignes de log concernées | 10 min | Logs exploitables en agrégation |

---

## DISCOVERED PROBLEMS

### P-01 · CRITICAL · Le secret est toujours dans l'historique Git

> **Note de rédaction (26/08/2026)** : la première version de ce document citait
> la valeur exacte de la clé cinq fois. Elle a été masquée en `arena-saer-****`.
> Un document qui décrit une fuite ne doit pas la reproduire : cela remettrait le
> secret dans l'historique et rendrait inutilisable tout scan automatique (T-03).
> L'erreur a été détectée par le contrôle de non-régression, pas par relecture.


**Emplacement** : **6 valeurs** réparties dans `librechat.yaml` et
`docker-compose.yml`, sur 44 commits d'historique.
**Cause** : les secrets ont été versionnés en clair pendant plusieurs mois. Les
correctifs successifs les ont retirés des fichiers, jamais de l'historique.
**Correction d'une affirmation antérieure** : ce document indiquait « `master`
(1 commit) » et les rapports d'audit aussi. Le dépôt a 44 commits ; le clone
d'audit était superficiel.
**Vérifié** : `git show 00e8f4f:librechat.yaml | grep apiKey` →
la ligne `apiKey:` avec la valeur en clair.
**Impact** : le dépôt est public. La clé est lisible par n'importe qui, et le
reste après un `git clone`. Elle protège la passerelle `/v1`, donc les 12 agents.
**Solution préparée** : `documents/RUNBOOK_PURGE_SECRETS.md`, sept étapes,
une commande à la fois. Outillage : `scripts/preparer_purge_secrets.py`.
La méthode a été vérifiée sur copie (voir *COMPLETED · T-01*).
**Statut** : **OUVERT — en attente du propriétaire.** Deux actions lui
appartiennent : la rotation des cinq clés (protège immédiatement) et
l'autorisation de réécrire l'historique (irréversible).

### P-02 · HIGH · Upload sans contrôle de type ni de taille

**Emplacement** : `apps/backend/routers/media.py`, `upload_video()`
**Cause** : `buffer.write(await file.read())` lit tout le fichier en mémoire ;
aucune extension n'est filtrée.
**Vérifié** : lecture du code — le seul contrôle est `Path(file.filename).name`,
qui bloque le path-traversal mais rien d'autre.
**Impact** : un fichier de plusieurs Go sature la RAM avant d'atteindre le
disque. Un `.exe` ou un `.ps1` est accepté dans `media/incoming/`.
**Atténuation actuelle** : la route exige désormais la clé API (correctif n°2),
ce qui la rend inatteignable depuis l'extérieur.
**Solution appliquée** : liste blanche de 12 extensions, plafond réglable,
écriture par blocs de 1 Mo, fichier partiel supprimé en cas de refus.
**Statut** : **RÉSOLU** le 26/08/2026 — voir *COMPLETED · T-02*. Mémoire mesurée
sur 64 Mo : 64,0 Mo de pic avant, 2,0 Mo après.

### P-03 · MEDIUM · Le chat ne cherche jamais d'information fraîche

**Emplacement** : `apps/backend/main.py`, `chat_stream_endpoint()` et
`get_arena_system_prompt()`
**Cause** : deux choses. D'une part aucun chemin du chat n'appelle
`WebSearchTool`. D'autre part le prompt système écrit en dur « Année actuelle :
2026 » et le nom du président et du premier ministre du Sénégal.
**Vérifié** : `grep "WebSearchTool" apps/backend/main.py` → aucun résultat.
**Impact** : une question d'actualité reçoit une réponse de mémoire du modèle,
présentée avec la même assurance qu'un fait vérifié. Écrire une date dans un
prompt ne donne aucune connaissance au modèle — cela lui donne juste de quoi
paraître à jour.
**Solution appliquée (moitié)** : le pipeline existe et est branché — recherche
→ lecture → synthèse avec sources citées, déclenché par l'intention `FRESH_INFO`.
**Statut** : **RÉSOLU** le 26/08/2026 (T-12 puis T-13). Le chat va vérifier, et
le prompt système n'affirme plus aucun fait daté. Reste ouvert, hors périmètre de
ce problème : le classement des sources par fiabilité (**T-14**).

### P-04 · MEDIUM · Budget VRAM déclaré supérieur à la carte

**Emplacement** : `.env.example`, `apps/backend/main.py:76-77`
**Cause** : deux modèles déclarés, `qwen2.5-coder:14b` et `qwen3.5:9b`, chacun
chargé avec `keep_alive: "30m"`.
**Vérifié** : lecture de la configuration uniquement. **Les tailles réelles n'ont
pas été mesurées** — aucun GPU ni Ollama sur la machine d'audit.
**Impact estimé** : si les deux modèles dépassent 12 Go cumulés, Ollama décharge
et recharge à chaque bascule d'agent, ce qui coûte plusieurs secondes.
**Solution proposée** : mesurer d'abord (voir *PERFORMANCE*), puis garder un seul
modèle chaud. → T-09, T-10, T-11
**Statut** : OUVERT — **hypothèse non mesurée, à ne pas traiter comme un fait.**

### P-05 · MEDIUM · `EXECUTE_COMMANDS` ne protège rien

**Emplacement** : `core/permissions/permission_manager.py` et ses appelants
**Cause** : `is_allowed()` n'est appelé que pour `PUBLISH` (publisher) et
`WRITE_FILES` (upload). `EXECUTE_COMMANDS` n'est lu nulle part.
**Vérifié** : `grep -rn "is_allowed"` → 2 appels seulement dans le code de
production.
**Impact** : la permission est déclarative. Ce qui bloque réellement l'exécution
de code, c'est le refus du bac à sable (correctif n°3), pas ce drapeau.
**Solution proposée** : deux lectures possibles, à trancher par le propriétaire —
soit l'assumer comme déclaratif, soit le brancher sur `SandboxInterpreterTool`,
ce qui désactiverait `CoderAgent` et `ReasoningEngine` par défaut.
**Statut** : OUVERT — **en attente d'une décision.**

### P-06 · MEDIUM · Le tag `qwen3.5:9b` n'est pas vérifié

**Emplacement** : `.env.example:17`, `apps/backend/main.py:77`,
`core/models/ollama_provider.py:13`
**Cause** : ce nom apparaît partout comme modèle par défaut mais n'a jamais été
confronté à `ollama list`.
**Vérifié** : rien — impossible ici, Ollama n'est pas joignable.
**Impact potentiel** : si le tag n'existe pas, Ollama peut répondre avec un autre
modèle sans rien signaler. Toutes les réponses viendraient d'un modèle non choisi.
**Solution proposée** : `ollama list` chez le propriétaire (T-09), puis corriger
le nom ou refuser de démarrer si le modèle est absent.
**Statut** : OUVERT — **`UNKNOWN`, pas `probablement faux`.**

### P-07 · LOW · Exceptions avalées dans le flux Ollama

**Emplacement** : `core/models/ollama_provider.py:76-77`
**Cause** : `except Exception: pass` dans la boucle de lecture du flux.
**Vérifié** : lecture du code.
**Impact** : une ligne malformée d'Ollama disparaît sans trace. Aucun diagnostic
possible en cas de comportement anormal du streaming.
**Solution proposée** : `logger.debug` au lieu de `pass`.
**Statut** : OUVERT

### P-08 · LOW · La documentation déclare terminé ce qui ne l'est pas

**Emplacement** : `docs/ROADMAP.md` lignes 25, 26, 28 ; `docs/NEXT_STEPS.md`
**Cause** : cases cochées sans test de validation.
**Vérifié** : les trois lignes existent toujours et affirment « Bac à sable
Docker actif », « Secrets déplacés vers `.env` et renouvelés », « tests fiables ».
Deux de ces trois affirmations sont **maintenant vraies** grâce aux correctifs 1,
3 et 6 — mais elles étaient fausses au moment où elles ont été écrites, et la
troisième (secrets) reste fausse tant que l'historique n'est pas purgé.
`docs/NEXT_STEPS.md` décrit encore la Phase 0 (« Créer README.md »).
**Impact** : c'est le défaut le plus durable des quatre rapports d'audit. Une
case cochée à tort empêche quiconque de revenir sur le problème.
**Solution appliquée** : affirmations décochées et expliquées, règle de tenue
posée en tête de `ROADMAP.md`, `NEXT_STEPS.md` réécrit, `CURRENT_TASK.md`
corrigé, et quatre garde-fous automatiques dans `tests/test_documentation.py`.
**Statut** : **RÉSOLU** le 26/08/2026 — voir *COMPLETED · T-06, T-07, T-08*.

### P-09 · LOW · Le frontend dépend d'un CDN

**Emplacement** : `apps/frontend/index.html:7` → `https://cdn.tailwindcss.com`
**Cause** : Tailwind chargé depuis Internet.
**Vérifié** : lecture du fichier.
**Impact** : sans connexion, l'interface s'affiche sans mise en forme. Cela
contredit la doctrine « local-first » revendiquée par le projet.
**Solution appliquée** : le fichier est embarqué dans
`apps/frontend/vendor/` et servi par le backend sur `/static/`, avec sa
provenance déclarée et vérifiée par test.
**Statut** : **RÉSOLU** le 26/08/2026. Mesuré dans Chromium, réseau coupé :
en-tête à 64 px (contre 137,875 px avant), aucune requête sortante.

---

## PERFORMANCE

**Aucune mesure de performance n'a été prise à ce jour.**

Ce n'est pas un oubli : la machine d'audit n'a **ni GPU NVIDIA, ni Ollama, ni
Docker actif**. Toute valeur inscrite ici sans mesure serait une invention.

Ce qui est certain, et vérifié par le code :

| Mesure | Valeur | Comment elle a été obtenue |
|---|---|---|
| Appels au modèle par message de chat | **2** (1 classification + 1 génération) | `POST /api/chat` avec un fournisseur scripté comptant ses appels |
| Appels au modèle avant le correctif n°9 | 3 | lecture du code : `chat_stream_endpoint` → `dispatch_request` → `orchestrator.run` |
| Contexte configuré | `num_ctx: 4096` | `core/models/ollama_provider.py` |
| Maintien en VRAM | `keep_alive: "30m"` | idem |
| Durée de la suite de tests | 5,7 s pour 364 tests | `pytest -q` |
| Pic mémoire, envoi de 64 Mo — avant T-02 | 64,0 Mo | `tracemalloc` sur l'ancien chemin |
| Pic mémoire, envoi de 64 Mo — après T-02 | 2,0 Mo | `tracemalloc` sur `ecrire_par_blocs` |

### À mesurer chez le propriétaire (T-09 à T-11)

Ces commandes sont à lancer **une par une**, sur la machine avec la RTX A2000,
Ollama démarré. Recopier les sorties dans ce document.

**1. Quels modèles sont réellement installés**
```
ollama list
```

**2. Ce qui est chargé en VRAM à l'instant T**
```
ollama ps
```

**3. VRAM réellement occupée sur la carte**
```
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

**4. Vitesse d'un modèle, chiffres officiels d'Ollama**
```
ollama run qwen2.5-coder:14b --verbose "Dis bonjour en une phrase."
```
La sortie donne `total duration`, `prompt eval rate` et `eval rate`
(jetons/seconde). Ce sont les chiffres à consigner.

Tableau à remplir une fois ces commandes passées :

| Modèle | Taille disque | VRAM occupée | Jetons/s | Temps 1er jeton | Contexte |
|---|---|---|---|---|---|
| `qwen2.5-coder:14b` | à mesurer | à mesurer | à mesurer | à mesurer | 4096 |
| modèle « profond » (nom à confirmer) | à mesurer | à mesurer | à mesurer | à mesurer | 4096 |

**Règle** : aucune optimisation de performance ne sera déclarée réussie sans un
avant/après chiffré dans ce tableau.

---

## ARCHITECTURE DECISIONS

Format : *Décision — pourquoi — ce que ça coûte si c'est faux.*

**AD-01 · Refuser plutôt que dégrader, pour l'exécution de code**
Sans bac à sable, l'exécution est refusée, jamais repliée silencieusement sur
l'hôte. Le repli survit derrière `ALLOW_UNSAFE_EXEC`, qui doit être posé
explicitement.
*Coût si c'est faux* : `CoderAgent` et `ReasoningEngine` ne fonctionnent plus
quand Docker est arrêté. C'est délibéré : mieux vaut une capacité indisponible
qu'une capacité dangereuse.

**AD-02 · Une autorisation ne se devine pas**
`ALLOW_UNSAFE_EXEC` n'accepte que `1`, `true`, `yes`, `oui`. Tout le reste — y
compris une valeur inattendue — vaut « non ».
*Coût si c'est faux* : un propriétaire qui écrit `ALLOW_UNSAFE_EXEC=vrai` ne
comprend pas pourquoi ça ne marche pas. Acceptable : l'erreur va dans le sens sûr.

**AD-03 · La classification d'intention passe par le modèle, avec repli annoncé**
Le modèle rapide choisit une étiquette dans une liste fermée. Hors liste ou
modèle injoignable → mots-clés, avec un avertissement dans les journaux.
*Coût si c'est faux* : chaque message coûte un appel de plus (~200 ms). C'est le
prix pour que « Calcule mon devis » ne parte plus vers l'agent qui exécute du code.

**AD-04 · Une classification par requête, transmise par le contexte**
L'étiquette calculée est passée via `context["intent"]` plutôt que mise en cache
dans l'agent.
*Coût si c'est faux* : un appelant qui oublie de la transmettre paie une
classification de plus. Un cache dans l'agent aurait rendu le résultat dépendant
d'un état invisible — pire à déboguer.

**AD-05 · `requirements.txt` = dépendances directes, `requirements.lock.txt` = gel**
Le gel d'origine est conservé mais n'est plus ce qui est installé.
*Coût si c'est faux* : deux fichiers à tenir à jour. En échange, le build Docker
Linux redevient possible et les versions installées sont choisies, pas héritées.

**AD-06 · Les tests exigeant un service portent le marqueur `integration`**
`pytest` est vert par défaut, hors ligne ; `pytest -m integration` exécute le reste.
*Coût si c'est faux* : 17 tests ne tournent jamais en CI et peuvent pourrir sans
qu'on le voie. Les supprimer aurait effacé la seule vérification que le bac à
sable isole réellement.

**AD-07 · Un double de test qui n'a pas de réponse lève une erreur**
`FakeProvider` refuse d'improviser.
*Coût si c'est faux* : les tests doivent déclarer combien d'appels au modèle ils
attendent. C'est plus verbeux — et c'est ce qui a permis de prouver que la boucle
d'auto-correction s'arrête bien.

**AD-08 · Licence propriétaire, tous droits réservés**
Décision du propriétaire, 26 août 2026 : le code ne doit être réutilisable par
personne pour l'instant.
*Coût si c'est faux* : aucune contribution extérieure possible. À revoir si le
projet doit s'ouvrir. **Une licence interdit ; elle n'empêche pas.** Un dépôt
public reste lisible et copiable — seul le passage en privé bloque réellement.

---

## Historique de ce document

| Date | Auteur | Modification |
|---|---|---|
| 2026-08-26 | Claude Code | Création. Audit initial, 9 correctifs consignés, 9 problèmes ouverts, 22 tâches en attente. |
| 2026-08-26 | Claude Code | T-02 terminée (contrôle des envois). P-02 résolu. Valeur de la clé masquée dans ce document. |
| 2026-08-26 | Claude Code | T-06, T-07, T-08 terminées (documentation alignée). P-08 résolu. Garde-fous documentaires ajoutés. |
| 2026-08-26 | Claude Code | T-01 préparée et vérifiée sur copie, non exécutée. Trois erreurs des rapports d'audit corrigées (44 commits, 6 secrets, commande destructrice). |
| 2026-08-26 | Claude Code | T-03 terminée (scan de secrets en CI). Règles propres au projet : les règles standard ne voyaient pas la clé de librechat.yaml. |
| 2026-08-26 | Claude Code | T-04 et T-05 terminées (limitation de débit, journalisation des refus). Priorité 1 close hors T-01. |
| 2026-08-26 | Claude Code | T-12 phase 1/3 : lecture d'une source web, avec refus des adresses internes. |
| 2026-08-26 | Claude Code | T-12 phase 2/3 : agent d'information fraîche, sources citées, refus sans source. |
| 2026-08-26 | Claude Code | T-12 terminée (3 phases). P-03 partiellement résolu. Défaut préexistant corrigé : l'intention annoncée par /api/chat. |
| 2026-08-26 | Claude Code | T-13 terminée (faits figés retirés du prompt système). P-03 résolu. |
| 2026-08-26 | Claude Code | T-19 phase 1/3 : empreinte de la surface HTTP, config.py, runtime.py. |
| 2026-08-26 | Claude Code | T-19 phase 2/3 : security.py et prompts.py extraits, tests redirigés vers le module propriétaire. |
| 2026-08-26 | Claude Code | T-19 terminée : main.py 652 → 61 lignes, 3 routeurs, comportement inchangé. |
| 2026-08-26 | Claude Code | Indexation documentaire phase 1/3 : lecture PDF/Word/texte avec provenance. |
| 2026-08-26 | Claude Code | Indexation documentaire phase 2/3 : inventaire, et documents personnels exclus de Git. |
| 2026-08-26 | Claude Code | Indexation documentaire terminée (3 phases). Indexation réelle à vérifier chez le propriétaire. |
| 2026-08-26 | Claude Code | Interface hors ligne : Tailwind embarqué, vérifié dans Chromium réseau coupé. P-09 résolu. |
| 2026-08-26 | Claude Code | CI de la PR #1 : test dependant de la profondeur du clone corrige. |

---

## 2026-08-26 — Réunion de la branche vidéo de Saer et de la branche d'ingénierie

**Point de départ.** Deux branches nées du même commit `00e8f4f` et jamais
reliées. Saer a travaillé sur sa machine sans jamais faire `git pull` après la
fusion de la demande #1 : il faisait tourner son code d'origine, ce qui explique
que trois correctifs vérifiés ici n'aient rien changé chez lui. Diagnostic établi
sur une preuve, pas sur une supposition — `[master c20eb17]` dans sa sortie de
`git commit`.

**Ce que sa branche apportait** : Studio Vidéo 1-clic, incrustation des
sous-titres (hardsub), transcription mot à mot, analyse Whisper. 2 commits,
6 fichiers, +417/−360.

**Ce que la même branche défaisait, mesuré :**

| | |
|---|---|
| `docker-compose.yml` | 4 valeurs de secrets remises en clair, à la place des `${...}` |
| `librechat.yaml` | une clé API vivante écrite en dur |
| `main.py` | `/api/chat/stream` et `/api/process-video` supprimées |
| `system_prompt()` | année et noms de responsables politiques réécrits en dur |

**Règle appliquée** : toutes ses fonctionnalités, aucune de ces régressions.

| Phase | Commit | Résultat |
|---|---|---|
| 1 — 4 fichiers vidéo repris tels quels | `c8132c9` | 384 tests |
| 2 — Studio porté en module (`apps/backend/studio.py`) | `ef650f4` | 403 tests |
| 3 — configuration : `env_file` gardé, secrets sortis | `c286716` | 413 tests |
| 4 — chaîne HTTP du Studio | `6659a96` | 416 tests |
| 5 — validation et reprise de ses mots-clés | *ce commit* | **424 tests** |

**Deux défauts de ce dépôt trouvés au passage, et corrigés :**

- **P-10.** `arena-fresh` était servi par `/v1/models` mais absent de
  `librechat.yaml`. Avec `fetch: false`, LibreChat n'affiche que cette liste :
  le modèle était **invisible dans le menu depuis sa création**, alors que la
  description de la demande #1 affirmait qu'il y avait été ajouté. Corrigé, et
  `tests/test_configuration_clients.py` tient désormais les deux listes
  ensemble.
- **P-11.** Le tri d'intention était confié au modèle seul. Un modèle dont les
  connaissances s'arrêtent avant l'année en cours **ne peut pas reconnaître
  qu'une question porte sur son futur** : « qui a gagné la coupe du monde
  2026 » était classé `CHAT`, puis répondu de mémoire — et faussement.
  `exige_verification` lit désormais l'horloge du système avant d'interroger le
  modèle (`c5ceaba`).

**Décisions :**

- *Le Studio vit dans `src`-style, pas dans `main.py`* — parce que la structure
  en modules est la règle du dépôt et qu'un `main.py` de 345 lignes est ce qu'on
  venait d'éliminer — **coût si c'est faux** : un fichier de plus à ouvrir pour
  comprendre la chaîne vidéo.
- *La liste de mots-clés de Saer est reprise, `combien` nu excepté* — parce
  qu'elle attrapait « population » et « coupe du monde » que la nôtre manquait —
  **coût si c'est faux** : des questions ordinaires partent inutilement sur le
  web et deviennent lentes.
- *Un test en double d'une garde existante est retiré, pas réparé* — parce que
  `test_surface_api.py` couvrait déjà les routes — **coût si c'est faux** : si
  cette garde est un jour affaiblie, plus rien ne rattrape la disparition d'une
  route.

**Ce qui reste dû au propriétaire** : la purge de l'historique (les 6 valeurs
fuitées y sont toujours, mais elles sont **mortes** depuis la rotation du
2026-08-26), et la branche `saer-video-wip` qui porte encore une clé en clair —
à supprimer une fois cette réunion validée.
