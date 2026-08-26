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
| **Branche de travail** | `claude/arena-personal-ai-qh66ix` (9 commits, non fusionnée) |
| **Branche de base** | `master` (1 commit, `00e8f4f`) |
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
7. **Le dépôt est public** et la clé `arena-saer-2026` reste dans l'historique
   Git au commit `00e8f4f`.

---

## COMPLETED

### 26 août 2026 — Correctifs de sécurité et de fiabilité (9 commits)

Branche `claude/arena-personal-ai-qh66ix`. Chaque entrée correspond à un commit.

---

**1. `fb83e98` — La clé API sort du dépôt**
*Fichiers* : `librechat.yaml`, `docker-compose.yml`, `.env.example`, `README.md`
*Changement* : `apiKey: "arena-saer-2026"` remplacé par `${ARENA_API_KEY}` ;
`docker-compose.yml` transmet la variable au conteneur LibreChat — elle manquait,
donc l'interpolation aurait donné une chaîne vide.
*Pourquoi* : secret en clair dans un dépôt public (V-01).
*Vérification* : `grep -rn "arena-saer-2026" . --exclude-dir=.git` → aucune
occurrence ; `docker compose config` → `ARENA_API_KEY: test-key` interpolée.
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

## IN PROGRESS

**Tâche courante** : audit technique complet du dépôt (§4 du prompt de référence)
et création de ce worklog.
**État exact** : audit terminé, worklog créé. Aucune modification de code dans
cette tâche.
**Prochaine action concrète** : décider avec le propriétaire de l'ordre des
tâches `PENDING`, en commençant par P-01 (historique Git).

---

## PENDING

Par priorité. Effort = estimation, à confirmer.

### Priorité 1 — Sécurité non close

| # | Tâche | Effort | Critère de validation |
|---|---|---|---|
| T-01 | Purger la clé de l'historique Git + rotation | 20 min | `git log -S "arena-saer-2026"` ne renvoie rien |
| T-02 | Filtrer les uploads : type + taille, écriture par blocs | 30 min | `.exe` → 415 ; fichier > 2 Go → 413 ; RAM stable |
| T-03 | Scan de secrets en CI (`gitleaks`) | 30 min | Un faux secret commité fait échouer la CI |
| T-04 | Limiter le débit sur `/api/chat` et `/v1/chat/completions` | 45 min | 11ᵉ requête en 1 min → 429 |
| T-05 | Journaliser les échecs d'authentification | 15 min | Une requête sans clé laisse une ligne de log |

### Priorité 2 — Alignement documentation ↔ code

| # | Tâche | Effort | Critère de validation |
|---|---|---|---|
| T-06 | Corriger les 3 affirmations fausses de `docs/ROADMAP.md` | 15 min | Chaque ligne cochée correspond au code |
| T-07 | Mettre `docs/NEXT_STEPS.md` à jour (il décrit encore la Phase 0) | 10 min | Contenu cohérent avec l'état réel |
| T-08 | Supprimer le doublon `RAPPORT_TRAVAIL.txt` (racine + `docs/`) | 5 min | Un seul fichier, fichiers identiques au md5 |

### Priorité 3 — Performance et matériel

| # | Tâche | Effort | Critère de validation |
|---|---|---|---|
| T-09 | Vérifier l'existence du tag `qwen3.5:9b` | 5 min | `ollama list` le montre, ou le nom est corrigé |
| T-10 | Arbitrer le budget VRAM : un seul modèle chaud | 1 h | VRAM mesurée < 12 Go, temps de bascule mesuré |
| T-11 | Mesurer et consigner les temps de réponse de référence | 45 min | Section *PERFORMANCE* remplie de vrais chiffres |

### Priorité 4 — Capacités (roadmap du prompt de référence)

| # | Tâche | Effort | Critère de validation |
|---|---|---|---|
| T-12 | Pipeline d'information fraîche : recherche → lecture → synthèse → sources citées | 4 h | « Quelle est la dernière version de Python ? » répond avec des sources datées |
| T-13 | Retirer les faits figés du prompt système, les remplacer par la mémoire ou le web | 30 min | Aucun fait daté écrit en dur dans `main.py` |
| T-14 | Routeur enrichi : besoin de fraîcheur, de RAG, d'outils, de vérification | 3 h | Le routeur renvoie une décision structurée, testée |
| T-15 | Passerelle de modèles par capacité (`fast_chat`, `coding`, `reasoning`…) | 3 h | Un agent demande une capacité, pas un nom de modèle |
| T-16 | Mémoire sémantique et mémoire utilisateur séparées | 4 h | Une information ancienne pertinente est retrouvée par similarité |
| T-17 | Indexation documentaire réelle (GraphRAG / LightRAG) | 3 h | Un document importé est interrogeable avec sa source |
| T-18 | Progression visible pendant les opérations longues | 2 h | L'interface affiche « recherche », « lecture », « génération » |

### Priorité 5 — Dette technique

| # | Tâche | Effort | Critère de validation |
|---|---|---|---|
| T-19 | Découper `main.py` en `routers/` | 2 h | Aucun fichier > 250 lignes, mêmes tests verts |
| T-20 | Tailwind servi en local (le CDN contredit le local-first) | 20 min | Interface stylée sans connexion réseau |
| T-21 | Accès SQLite non bloquant depuis les routes `async` | 2 h | Charge concurrente sans blocage mesuré |
| T-22 | Retirer les emojis des 4 lignes de log concernées | 10 min | Logs exploitables en agrégation |

---

## DISCOVERED PROBLEMS

### P-01 · CRITICAL · Le secret est toujours dans l'historique Git

**Emplacement** : commit `00e8f4f`, `librechat.yaml:7`
**Cause** : la clé a été versionnée dès le premier commit. Le correctif du
26 août l'a retirée du fichier, pas de l'historique.
**Vérifié** : `git show 00e8f4f:librechat.yaml | grep apiKey` →
`apiKey: "arena-saer-2026"`.
**Impact** : le dépôt est public. La clé est lisible par n'importe qui, et le
reste après un `git clone`. Elle protège la passerelle `/v1`, donc les 12 agents.
**Solution proposée** :
1. **Générer une nouvelle clé** et la mettre dans `.env` — c'est la seule action
   qui neutralise vraiment l'ancienne.
2. Purger l'historique (`git filter-repo`) — opération destructive, réécrit tous
   les commits, casse les clones existants. **Nécessite l'accord explicite du
   propriétaire.**
3. Repasser le dépôt en privé le temps de l'opération.
**Statut** : **OUVERT** — la rotation dépend du propriétaire, la purge aussi.

### P-02 · HIGH · Upload sans contrôle de type ni de taille

**Emplacement** : `apps/backend/main.py`, `upload_video()`
**Cause** : `buffer.write(await file.read())` lit tout le fichier en mémoire ;
aucune extension n'est filtrée.
**Vérifié** : lecture du code — le seul contrôle est `Path(file.filename).name`,
qui bloque le path-traversal mais rien d'autre.
**Impact** : un fichier de plusieurs Go sature la RAM avant d'atteindre le
disque. Un `.exe` ou un `.ps1` est accepté dans `media/incoming/`.
**Atténuation actuelle** : la route exige désormais la clé API (correctif n°2),
ce qui la rend inatteignable depuis l'extérieur.
**Solution proposée** : liste blanche d'extensions, plafond de taille, écriture
par blocs de 1 Mo. → T-02
**Statut** : OUVERT

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
**Solution proposée** : pipeline recherche → lecture → extraction → synthèse
avec sources citées, déclenché par le routeur. → T-12, T-13, T-14
**Statut** : OUVERT

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
**Solution proposée** : T-06, T-07.
**Statut** : OUVERT

### P-09 · LOW · Le frontend dépend d'un CDN

**Emplacement** : `apps/frontend/index.html:7` → `https://cdn.tailwindcss.com`
**Cause** : Tailwind chargé depuis Internet.
**Vérifié** : lecture du fichier.
**Impact** : sans connexion, l'interface s'affiche sans mise en forme. Cela
contredit la doctrine « local-first » revendiquée par le projet.
**Solution proposée** : T-20.
**Statut** : OUVERT

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
| Durée de la suite de tests | 3,0 s pour 125 tests | `pytest -q` |

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
