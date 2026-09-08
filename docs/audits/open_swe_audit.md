# Audit Open SWE — ce qu'ARENA a déjà, ce qui manque, ce qui se fusionne

*Mesuré le 08/09/2026. Dépôt audité : `langchain-ai/open-swe`, commit
`342559af5d7c56364601212f7632482892ce8583` (clone superficiel), licence MIT.*

Mission du propriétaire : exploiter les meilleures capacités d'Open SWE pour
renforcer le Software Engineering d'ARENA, sans créer un deuxième agent de
code indépendant. Ce document est l'étape 2, 3 et 4 de cette mission — audit
ARENA, audit Open SWE, comparaison — avant tout code.

**Note ajoutée après coup, en fusionnant sur `master` (voir DEC-0073) :** une
session parallèle a reçu la même mission et l'a déjà travaillée sous
DEC-0063 et DEC-0072 — mini-SWE-agent (garde-fous de boucle) et la reprise
de tâche interrompue. Ce document reste tel qu'écrit le 08/09/2026 ; la
décision finale, avec les deux fusionnées, est DEC-0073 dans
`docs/DECISIONS.md`.

---

## 1. Audit ARENA — ce qui existe déjà

Quatre entrées séparées vers le code, choisies par le classificateur à
mots-clés de `agents/orchestrator/orchestrator_agent.py`
(`_classer_par_mots_cles`), routées par une suite de `if/elif` dans
`apps/backend/routers/chat.py`. **Aucune des quatre ne se connaît des
trois autres.**

| Intention (mot-clé) | Agent | Ce qu'il fait réellement |
|---|---|---|
| `ATELIER` | `DioumtoukayAgent` (`agents/dioumtoukay/`) | Le seul qui **agit** : boucle multi-tours, une action par tour (lire/écrire/remplacer/chercher/lister/déplacer/exécuter), via `tools/atelier/atelier.py`. Git en shell nu. Plafonné à 12 tours. **Aucune sandbox** — DEC-0038, décision du propriétaire prise en connaissance de cause, non renégociée ici. |
| `CODE_EXECUTION` | `CoderAgent` (`agents/coder/`) | Script Python **isolé**, généré puis exécuté dans le bac à sable Docker (DEC-0004), 2 essais d'auto-correction. Aucun accès au dépôt. |
| `SWE_FIX` | `SWEAgent` (`agents/swe_agent/`) | Lecture seule. Recherche façon ACI (Princeton), **propose** une correction, ne modifie jamais rien. |
| `REPO_ENGINEERING` | `RepoEngineerAgent` (`agents/repo_engineer/`) | Lecture seule. Lit l'arborescence, **propose** un plan d'architecture, ne modifie jamais rien. |

**Le défaut le plus coûteux** : `SWEAgent` et `RepoEngineerAgent` sont des
culs-de-sac. Leur analyse ne sert jamais à Dioumtoukay — le propriétaire doit
deviner, par le mot-clé de sa phrase, laquelle des quatre portes ouvrir. Une
tâche de réparation réelle a besoin des trois : comprendre l'architecture,
localiser le bug, puis corriger et vérifier.

**Ce qu'ARENA porte déjà, et sur quoi la fusion s'appuie :**

- **`core/connectors/base.py` + `core/connectors/registre.py`** — le contrat
  `Connecteur` (capacités déclarées, santé mesurée jamais supposée,
  `ResultatAction` typé, permission vérifiée avant tout) et un registre à
  fabriques paresseuses, tolérant à la panne d'un connecteur. C'est
  l'emplacement naturel d'un connecteur GitHub — **qui n'existe pas
  aujourd'hui**.
- **`config/permissions_services.yaml` + `core/permissions/controle.py`** —
  `ALLOWED` / `CONFIRMATION` / `DENIED`, par service et action, avec des
  coupe-circuits globaux qu'aucune configuration fine ne peut lever. Le
  modèle exact que la mission demande au §16.
- **`core/execution/travaux.py` (`FileDeTravaux`)** — travail de fond,
  `PENDING/RUNNING/DONE/FAILED/CANCELLED`, parallélisme borné, progression
  `faits/total` jamais inventée. **En mémoire seulement** — ne survit pas à
  un redémarrage du serveur.
- **`core/production/disponibilite.py`** — le patron « une capacité,
  plusieurs porteurs, chacun sondé pour de vrai » (déjà utilisé pour la
  vidéo). C'est le patron que `software_engineering` doit suivre : la
  disponibilité vient de la sonde du connecteur, jamais d'une seconde
  logique qui pourrait diverger.
- **Persistance SQLite par module** (`core/actions/attente.py`,
  `core/conversations/depot.py`, `core/memory/*`) — le patron à suivre pour
  un état de tâche SWE qui survit à un redémarrage.
- **Aucun connecteur GitHub.** Le seul accès à git est `Atelier.executer(["git", ...])`
  en shell. Pas de PR, pas de lecture de CI, pas de commentaires de revue.
  C'est le manque le plus net face à Open SWE.

---

## 2. Audit Open SWE — ce qu'il apporte réellement

Contrairement à l'attente initiale (dépôt TypeScript), **l'agent lui-même est
en Python** (`pyproject.toml` : `python_version = "3.14"`), construit sur
LangGraph + la bibliothèque `deepagents` de LangChain. Seuls le tableau de
bord et le site restent en TypeScript (`ui/`, `desktop/`).

**Cinq graphes** (`langgraph.json`) : `agent` (la boucle de code), `reviewer`,
`analyzer`, `chat`, `scheduler`. C'est la même décomposition que la mission
demande au §10 — Analyzer / Coder / Reviewer — et elle recoupe presque
exactement `RepoEngineerAgent` (analyzer) et `SWEAgent` (le grain de la
recherche chirurgicale) côté ARENA. **Ce qui manque à ARENA : un rôle
`reviewer`, et le fait que ces rôles collaborent au lieu d'être trois portes
séparées.**

**GitHub — la partie la plus aboutie, et la plus directement utile**
(`agent/github/`) : création et complétion de *check runs* sur le SHA de la
PR (`checks.py`), état combiné de la CI par lot en GraphQL
(`pull_request_checks.py`), commentaires de revue (`comments.py`, 588
lignes), webhooks (`webhook.py`, 1258 lignes). **Chaque appel est
best-effort** — une permission GitHub manquante ne fait jamais tomber le
reste, exactement la discipline du contrat `Connecteur` d'ARENA
(`sonder()` ne lève jamais).

**Le point de contrôle humain n'est pas une interruption au milieu de
l'exécution** (pas de `interrupt()` LangGraph trouvé sur le chemin de code
exploré) : c'est la **PR elle-même**, ouverte en **brouillon par défaut**
(`profile_draft_prs`, `agent/dashboard/agent_overrides.py:89`, défaut
`True`). L'agent travaille seul jusque-là ; un humain décide de la marquer
prête et de fusionner.

**Sandbox** (`agent/sandboxes/providers/`) : un registre à plusieurs
fournisseurs — `local.py`, `e2b.py`, `daytona.py`, `modal.py`, `runloop.py`.
L'idée transportable est le **registre**, pas les fournisseurs : tous sauf
`local` sont des services payants tiers auxquels le propriétaire n'a pas de
compte, et en ajouter un ici serait inventer un fournisseur qu'il n'a pas
demandé.

**Exécution de fond** (`agent/background_tasks.py`, `agent/scheduler.py`) :
surveillance via les *crons* de leur propre serveur LangGraph déployé
(`get_client(url=langgraph_url())`). **Non transportable tel quel** : ça
suppose une infrastructure LangGraph déployée, qu'ARENA n'a pas et n'a pas de
raison d'adopter (ce serait exactement le « deuxième moteur d'orchestration »
que la mission interdit).

**Dépendances** : `deepagents`, `langgraph`, `langchain-anthropic`,
`langchain-openai`, `langchain-fireworks`, `langchain-daytona`,
`langchain-modal`, `langchain-e2b`, `langchain-runloop`. Aucune n'entre dans
ARENA — les adopter romprait la règle « pas de deuxième agent de code
indépendant » au niveau le plus profond : celui du framework
d'orchestration.

---

## 3. Comparaison, capacité par capacité

| Capacité | ARENA | Open SWE | Verdict |
|---|---|---|---|
| Boucle d'action (lire/écrire/exécuter) | Dioumtoukay, 12 tours, texte structuré | Deep Agents, appels d'outils LangChain natifs | **ARENA suffit** — remplacer la boucle romprait DEC-0038 et le contrat de Dioumtoukay pour un gain non mesuré |
| Analyse d'architecture | `RepoEngineerAgent`, lecture seule, isolé | Graphe `analyzer`, alimente le reste | **COMBINE** — même rôle, mal câblé côté ARENA : à brancher comme outil de Dioumtoukay |
| Recherche chirurgicale de bug | `SWEAgent`, protocole ACI, isolé | Fait partie du graphe `agent` | **COMBINE** — même raison |
| Revue de code après coup | Absent | Graphe `reviewer` dédié | **BETTER OPEN SWE** — à construire côté ARENA, en réutilisant le style lecture-seule de `SWEAgent`/`RepoEngineerAgent` |
| Sandbox d'exécution | Docker local (DEC-0004), et **aucune** pour Dioumtoukay (DEC-0038) | Registre à 5 fournisseurs payants + local | **ÉQUIVALENT en local** — les fournisseurs payants ne sont **PAS UTILES** ici : aucun compte, aucune demande |
| GitHub — lecture, PR, CI, revue | **Absent** | Complet, best-effort, robuste | **BETTER OPEN SWE** — à construire, en s'inspirant de la forme (jamais lever, jamais bloquer le reste), jamais du code (Python vs TypeScript à part l'agent, mais surtout : dépendances GitHub App propres à leur déploiement) |
| Permissions | `ALLOWED/CONFIRMATION/DENIED`, coupe-circuits globaux | Point de contrôle unique : PR en brouillon | **BETTER ARENA** — plus fin, déjà éprouvé (Gmail, Calendar, réseaux sociaux) ; le brouillon Open SWE **s'ajoute**, il ne remplace rien |
| Tâches de fond / durabilité | `FileDeTravaux`, en mémoire, non résilient à un redémarrage | *Crons* sur leur propre serveur LangGraph déployé | **NOT USEFUL** tel quel côté Open SWE (suppose leur infra) — mais leur **existence** justifie de rendre `FileDeTravaux` persistant, à la façon SQLite déjà utilisée ailleurs dans ARENA |
| Modèle utilisé | `ModelProvider` déjà abstrait (Ollama, distant) | Sélection de modèle par profil (Anthropic/OpenAI/Fireworks) | **ÉQUIVALENT** — les deux sont déjà agnostiques ; rien à fusionner |
| Observabilité | `JournalDesActions`, un journal par action | `task_id`, statut par graphe, tableau de bord dédié | **COMBINE** — le journal existe, il manque un identifiant de tâche SWE qui le traverse en entier |

---

## 4. Décision

Voir `docs/DECISIONS.md`, **DEC-0073**.

Résumé : une capacité canonique `software_engineering`, portée par un
orchestrateur SWE propre à ARENA (pas LangGraph, pas `deepagents`), qui
choisit entre les backends existants (Dioumtoukay pour le travail réel,
CoderAgent pour un script isolé) et les fait collaborer avec
`RepoEngineerAgent` et `SWEAgent` comme outils internes plutôt que comme
portes séparées. Un connecteur GitHub est créé — le premier du dépôt — suivant
le contrat `Connecteur` existant, avec la création de PR **derrière
`CONFIRMATION`** et **en brouillon par défaut**. Aucune dépendance à
`langgraph`/`deepagents`/aux fournisseurs de sandbox payants.
