# Audit — Agent Orchestrator (AO) et le système d’ingénierie d’ARENA

*Décision demandée le 30/09/2026 : évaluer le dépôt courant
`Untrivial-ai/agent-orchestrator` contre les mécanismes d’orchestration et de
développement logiciel **déjà exécutés** dans ARENA. Il ne s’agissait pas de
trouver un prétexte pour installer AO : une intégration devait prouver un gain
borné, sans deuxième runtime, sans nouvelle surface de fuite ni de contrôle.*

## Décision

**Option C — référence architecturale seulement.**

AO est un produit complet de supervision de développeurs-agent : daemon Go,
base SQLite, runtimes PTY, adaptations d’agents, worktrees, observateur SCM,
interface Electron/React, CLI, mobile et composantes cloud. Ce n’est ni une
bibliothèque Python ni un adaptateur d’une capacité unique. L’ajouter à ARENA
créerait précisément un second orchestrateur, un second état de sessions, un
second gestionnaire de worktrees, une seconde interface GitHub/CI/revue et un
second plan de contrôle local — alors que les primitives dont ARENA a besoin
existent déjà sous une forme gouvernée.

**Rien n’entre dans ARENA :** aucun paquet, sous-module, binaire, processus AO,
connecteur, frontend, schéma SQLite, clé, configuration, télémétrie, ni code
copié. AO n’est pas démarré par les tests et aucune donnée de dépôt ARENA n’est
transmise à AO ou à un tiers.

Un essai personnel d’AO, installé et configuré séparément par son propriétaire,
reste un choix externe à ce dépôt — **ce n’est pas une intégration ARENA**. Il
ne doit jamais être présenté comme un composant du runtime d’ARENA ni comme sa
source de vérité.

---

## 0. Méthode et périmètre de preuve

| Élément | Mesure |
|---|---|
| Amont audité | `https://github.com/Untrivial-ai/agent-orchestrator` (l’ancien lien `ComposioHQ/agent-orchestrator` résout vers le même dépôt courant) |
| Révision lue | `daeff885b57685b4690ececb25d4fc330b69783d`, clone superficiel local d’inspection au 30/09/2026 |
| Licence amont | Apache-2.0 (`LICENSE` lu) |
| Sources AO lues | daemon/configuration/télémétrie, registre d’agents, gestionnaire de sessions, lifecycle/reaper, worktree, observateur SCM, services PR/revue, migrations SQLite, frontend Electron/React et documentation d’exploitation |
| Sources ARENA lues | routeur, spécialistes code, Dioumtoukay, coordination/reprise/travaux, équipes/espaces de travail, Atelier/Git/verrous, connecteur GitHub, runtime, frontière de confiance et décisions associées |
| Exécution AO | **Aucune.** Ni dépendance, ni binaire, ni daemon, ni interface n’ont été installés ou démarrés. |
| Cloud AO privé | **UNKNOWN — non mesuré.** Le dépôt public décrit un contrat et des chemins cloud, mais le backend cloud privé n’est pas présent dans le clone. |
| Comparaison de performance / coûts / qualité d’agent | **UNKNOWN — non mesuré.** Aucun benchmark équitable n’existe ici et aucun ne serait une raison de transférer un dépôt privé à un produit tiers. |

Les affirmations de cet audit portent donc sur des chemins source et des
comportements configurés, pas sur les slogans du README. Les fichiers amont ne
sont pas copiés dans ARENA.

---

## 1. ARENA avant AO : ce qui est réellement en place

ARENA n’est pas vide sur laquelle poser un orchestrateur. Ses rôles sont séparés
pour éviter qu’un agent de diagnostic, un agent de code et un système de Git
s’attribuent le même état ou la même autorité.

| Besoin à comparer | Implémentation ARENA exécutée | État / frontière utile à la décision |
|---|---|---|
| Aiguillage | `agents/orchestrator/orchestrator_agent.py`, atteint depuis `apps/backend/routers/chat.py` | Classe les intentions, dont `SWE_FIX`, `REPO_ENGINEERING`, `ATELIER` et `EQUIPE`; ce n’est pas un daemon de sessions concurrent. |
| Lecture d’architecture / bug | `agents/repo_engineer/repo_engineer_agent.py`, `agents/swe_agent/swe_agent.py` | Lecture seule; interroge d’abord `codebase_memory`, puis les replis déclarés. Ces agents proposent, ils n’écrivent pas. |
| Exécution de code réelle | `agents/dioumtoukay/dioumtoukay_agent.py` + `tools/atelier/atelier.py` | Dioumtoukay est le propriétaire autorisé de l’exécution d’ingénierie (DEC-0038), avec actions une à une, budget, journal, résultats réels et rapport. |
| Contexte du code | `core/connectors/codebase_memory.py`, `RepoEngineerAgent`, `SWEAgent` | Index/graphe de code local via le connecteur existant; pas de transfert automatique du dépôt à AO. |
| Tâches et récupération | `core/execution/coordination.py`, `core/execution/reprise.py`, `core/execution/travaux.py`, `core/execution/journal_disque.py` | États explicites, reprises bornées, vérification, journal atomique. Une action interrompue est dite inconnue et n’est pas rejouée aveuglément. |
| Collaboration et parallélisme logique | `core/agent/collaboration.py`, `core/agent/equipe.py`, `core/agent/espace_de_travail.py` | Décomposition, délégation par capacité, état partagé de projet persistant et tâches reliées à une racine. Ce n’est pas une flotte de PTY. |
| Worktrees et concurrence d’écriture | `tools/atelier/atelier.py::isoler()` / `nettoyer_worktree()`, `tools/atelier/verrous.py` | Worktree Git isolé, protection `.worktrees/`, aucun `--force` implicite sur un worktree sale; verrous canonisés par fichier et verrou Git par dépôt. |
| Git mutationnel sûr | `tools/atelier/git_etat.py`, `tools/atelier/git_ops.py` | État/diff structurés, préconditions de HEAD, opérations idempotentes, postconditions et journal. |
| GitHub, PR, CI et revue | `core/connectors/github.py`, câblé par `apps/backend/runtime.py` et Dioumtoukay | Lecture de dépôt/diff, création de branche, écriture ciblée, PR toujours brouillon après confirmation, état/diagnostic CI et commentaires de revue. |
| Instructions et contenu externe | `core/security/trust.py` | Sorties de dépôt, GitHub, CI, outils et agents restent des données non fiables; elles ne peuvent pas promouvoir une instruction système. |

Les décisions existantes sont déterminantes :

- **DEC-0038** : Dioumtoukay est l’agent d’ingénierie auquel le propriétaire a
  accordé le droit d’agir; DEC-0014 conserve son rôle de gardien lecture/rapport.
- **DEC-0063** : les rôles `RepoEngineerAgent`, `SWEAgent`, `CoderAgent` et
  Dioumtoukay sont complémentaires; pas de deuxième coding agent.
- **DEC-0072/0073** : reprise durable et connecteur GitHub, dont PR brouillon,
  CI et revue, ont déjà été décidés et implémentés.
- **DEC-0091** : worktrees, verrous de fichiers et action amorcée/confirmée;
  explicitement pas un second runtime de code.
- **DEC-0093/0094** : Git reste structuré, préconditionné, vérifié et
  idempotent.
- **DEC-0113/0114** : le coordinateur existant porte la persistance/reprise; un
  second orchestrateur n’est pas la réponse.

### Écarts réels, sans les déguiser

AO est plus large qu’ARENA sur trois aspects : sessions de coding-agent
persistantes avec TTY/PTY, observateur SCM continu et Kanban desktop/mobile.
ARENA offre les capacités GitHub à la demande et la coordination durable, mais
ne lance pas une seconde application Electron ni une flotte de terminaux
persistants.

C’est un **écart de produit**, pas une capacité minuscule manquante. Aucun
besoin utilisateur mesuré ne demande aujourd’hui un tableau de bord permanent
ou des dizaines d’agents CLI concurrents. Ajouter tout AO pour ces trois
fonctions ferait entrer plus de système que de valeur.

---

## 2. AO audité dans son implémentation

### 2.1 Architecture et persistance

La source publique confirme que AO est une application complète :

- `backend/internal/daemon/daemon.go` construit un daemon Go long vivant,
  serveur HTTP loopback, SQLite, fan-out CDC/SSE, lifecycle, terminaux,
  navigateur, services de session/PR/revue et observateurs;
- `backend/internal/session_manager/manager.go` possède le cycle de session :
  création d’espace, démarrage, rollback d’un spawn raté, arrêt, restauration,
  réconciliation au démarrage et réconciliation en arrière-plan;
- `backend/internal/storage/sqlite/` et ses migrations possèdent projets,
  sessions, conversations, PR, revues, notifications, usage et événements;
- `frontend/` est une application Electron/React avec son propre OpenAPI,
  terminal, mises à jour, profil local et état interface;
- `backend/internal/adapters/agent/registry/registry.go` enregistre plus de
  trente adaptations de harnesses de code (dont Claude Code, Codex, OpenCode,
  Cursor, Gemini, Copilot, Cline et Aider), au lieu de réutiliser les agents et
  fournisseurs d’ARENA.

Les données et le protocole AO vivent sous `~/.ao` par défaut, ou sous
`AO_DATA_DIR`; ce SQLite n’est pas l’état ARENA. Deux sources de vérité pour les
mêmes projets, branches, tâches et revues produiraient des divergences plutôt
qu’une intégration.

### 2.2 Sessions, worktrees et supervision

AO donne à un worker Git un branchement et un worktree isolés, ou un répertoire
standalone pour un worker sans projet. Le gestionnaire de sessions gère aussi
les restaurations et les échecs de provisioning; l’observateur/reaper et les
runtimes tmux/ConPTY/PTY supervisent les processus. Le code de worktree refuse
la destruction forcée du worktree enregistré et sale dans le chemin normal.

Ce sont de bonnes références de conception : rollback explicite, propriétaire
du workspace clairement nommé, réconciliation après redémarrage, et suppression
prudente. Elles ne sont pas une API embeddable. ARENA possède déjà la primitive
qui répond à son besoin courant — `Atelier.isoler()` et `nettoyer_worktree()` —
et son test réel couvre l’isolation et le refus de détruire un worktree modifié.

### 2.3 PR, CI, revue et GitHub

`backend/internal/observe/scm/observer.go` persiste des faits SCM/PR/CI/revue,
utilise des garde-fous de pagination/ETag/rate limit et ne fait avancer son
curseur de synchronisation qu’après la persistance et le lifecycle. Les services
PR/revue peuvent ramener du feedback au worker, et les sessions portent des
politiques d’auto-injection CI/revue.

La qualité de l’observateur est réelle, mais l’intégrer signifierait donner à AO
un deuxième mandat GitHub et faire remonter des sorties GitHub/CI/revue — contenu
non fiable — dans un autre système d’instructions. ARENA a déjà son connecteur
GitHub, ses limitations de taille et sa frontière `TrustLevel.EXTERNAL`.
Aucune route AO ne devient donc une autorité ARENA.

### 2.4 Dépendances et exploitation

AO exige son propre écosystème : Go 1.27.1 (`backend/go.mod` et CI), Node/npm,
Electron, React, SQLite, OpenAPI/codegen, PTY/tmux ou ConPTY, agents CLI,
artefacts de navigateur et une chaîne de packaging multi-plateforme. Le
`frontend/package.json` embarque notamment Electron, `better-sqlite3`,
`posthog-js`, `@sentry/electron`, Electron updater et de nombreuses dépendances
interface/runtime.

ARENA est un backend Python/FastAPI avec ses abstractions locales. Importer AO
ne serait ni une dépendance Python supplémentaire ni un simple sous-processus :
ce serait exploiter et sécuriser une deuxième application complète. Cela heurte
la discipline de dépendance de DEC-0008 et les exclusions de DEC-0091.

---

## 3. Télémétrie, réseau et vie privée — constat exact

La télémétrie est un bloqueur suffisant pour exclure tout usage AO par défaut
dans le runtime ARENA. Les protections annoncées par AO réduisent des données,
mais elles ne rendent pas l’envoi nul et elles ne respectent pas l’exigence
ARENA « aucune télémétrie externe par défaut ».

### 3.1 Ce qui est envoyé et quand

La documentation AO `docs/telemetry.md` et les producteurs confirment :

| Producteur | Déclenchement par défaut en release desktop empaquetée | Destinataire / données significatives |
|---|---|---|
| Renderer Electron | `frontend/src/shared/telemetry.ts::rendererTelemetryEnabled()` retourne `isPackaged` quand `AO_TELEMETRY_RENDERER` est absent. | PostHog direct, hôte embarqué `https://us.i.posthog.com`, identifiant installation aléatoire `ins_…`, version/OS/canal/surface, événements d’usage et identifiants projet/session hachés lorsque nécessaires. |
| Daemon lancé par Electron | `frontend/src/main.ts::telemetryOverrides()` injecte par défaut `AO_TELEMETRY_EVENTS=on`, `AO_TELEMETRY_REMOTE=posthog`, clé PostHog et hôte en release. | PostHog via `PostHogSink`; allowlist d’événements et de propriétés, dont types de harness, états/erreurs, durée et activité de session. |
| GitHub dans ces événements | Projet ajouté/créé : `github_org`; session démarrée : `github_actor` (`backend/internal/adapters/telemetry/posthog.go`). | Le propriétaire de remote GitHub (organisation **ou compte personnel**) et le nom d’utilisateur GitHub authentifié sont envoyés. La doc AO reconnaît explicitement que ces valeurs ne sont pas anonymes. |
| Connexion elle-même | À chaque réception PostHog. | PostHog reçoit IP et métadonnées appareil; AO laisse la géolocalisation grossière IP (pays/région/ville selon disponibilité) active. |
| Sentry daemon | `telemetryOverrides()` transmet `DEFAULT_SENTRY_DSN` en release sauf valeur explicite; le daemon lit `AO_SENTRY_DSN`. | Captures de pannes 5xx/panics selon sa configuration. Le canal séparé agent-switch est annoncé désactivé en production, mais cela ne retire pas le chemin Sentry daemon général configuré par le superviseur. |

AO déclare ne pas envoyer intentionnellement code source, diffs, prompts,
conversations, terminal, arguments shell, noms de dépôt/branche, chemins en
clair ni secrets. Les sources montrent aussi une allowlist, redaction de chemin,
limitation de débit, identifiants hachés et session recording désactivé. Ces
propriétés sont positives, mais elles ne changent pas les transmissions
explicites d’identité GitHub, de métadonnées et d’IP.

La politique de « Event reporting » de l’interface concerne le chemin de
fiabilité agent-switch; le source `buildTelemetryBootstrap()` précise que ce
contrôle ne désactive pas l’analytics PostHog. Il ne suffit donc pas de couper
ce réglage visuel.

### 3.2 Désactivation : possible, mais non satisfaisante comme intégration

AO documente, pour un desktop, les variables suivantes à placer dans **le
processus Electron réellement lancé**, puis un redémarrage :

```bash
AO_TELEMETRY_RENDERER=off
AO_TELEMETRY_EVENTS=off
AO_TELEMETRY_REMOTE=off
AO_SENTRY_DSN=""
```

Les trois premières désactivent respectivement les événements renderer directs,
la capture daemon (y compris sa copie SQLite) et l’export daemon PostHog. La
quatrième est nécessaire pour ne pas laisser le superviseur empaqueté injecter
son DSN Sentry par défaut; une chaîne vide est une valeur explicite que son
code conserve et qui laisse le sink Sentry inactif. `AO_TELEMETRY_DISABLED_EVENTS`
ne coupe que des flux nommés et **préserve** le stockage SQLite local : ce n’est
pas un opt-out complet. Pour le mobile, les contrôles sont différents et
compilés (`EXPO_PUBLIC_AO_TELEMETRY_DISABLED=1` / liste d’événements).

**UNKNOWN — non mesuré :** aucune capture réseau d’un binaire AO empaqueté avec
ces quatre variables n’a été exécutée. Le code et la documentation prouvent les
portes de désactivation prévues; ils ne remplacent pas une mesure de trafic de
toutes les dépendances d’une release. C’est précisément pourquoi ARENA ne doit
pas conditionner sa confidentialité à ce montage externe.

---

## 4. Matrice de décision

| Domaine candidat | AO | ARENA actuel | Verdict |
|---|---|---|---|
| Worktree isolé | Worker Git = branche/worktree, cycle de vie géré | `Atelier.isoler()` / `nettoyer_worktree()`, protection `.worktrees/`, verrous et Git sûr | Déjà couvert pour le besoin démontré; garder la primitive ARENA. |
| Sessions workers persistantes | PTY/tmux/ConPTY, reaper, restauration, nombreux CLI | Dioumtoukay durable avec reprise d’actions; pas de flotte de PTY | Écart réel, mais produit entier sans besoin démontré; pas d’adaptateur AO. |
| Travail parallèle | Workers/worktrees + Kanban | équipes, coordination, espaces de travail, verrous de fichiers/dépôt | ARENA couvre la coordination sûre; ne pas multiplier les travailleurs concurrents sans demande explicite. |
| Cycle de tâche / reprise | SQLite/session reducer/reconcile | `Coordination`, `JournalDeReprise`, travaux persistants, états inconnus après crash | Même objectif avec source de vérité ARENA; ne pas dupliquer l’état. |
| PR / CI / revue | Observateur SCM continu et feedback worker | Connecteur GitHub à la demande, PR brouillon confirmée, CI/diagnostic/revue | Partiel sur l’observation continue, mais pas un motif pour installer une application complète. |
| Supervision d’agent | Adapters CLI + PTY + UI native | Dioumtoukay/Atelier + fournisseurs ARENA | Incompatible par nature : AO superviserait ses propres agents et ses propres credentials. |
| Orchestration projet | Orchestrateur AO persistant au-dessus de ses workers | routeur, `EQUIPE`, collaboration et espace de travail ARENA | Deux orchestrateurs décideraient de la même tâche; rejet. |
| Télémetrie / confiance | PostHog/Sentry distants activés par défaut dans release, GitHub identity/IP | exécution locale, connecteurs explicites, frontière de confiance | Incompatible par défaut; aucun passage de données/repo vers AO. |

### Les quatre options demandées

| Option | Résultat | Motif |
|---|---|---|
| **A — dépendance runtime** | Rejetée | AO n’est pas une bibliothèque : daemon/UI/SQLite/runtimes/télémétrie/credentials parallèles. |
| **B — intégration développeur optionnelle** | Rejetée comme changement ARENA | Un wrapper ne supprimerait pas son second état, ses CLI, son plan de contrôle ou sa télémétrie par défaut. Le bénéfice spécifique n’est pas mesuré. |
| **C — référence architecturale** | **Retenue** | Ses patterns de rollback, réconciliation, propriété de workspace et observation robuste sont documentés pour une future capacité ARENA, sans reprendre son runtime. |
| **D — aucune référence** | Rejetée | L’audit a une valeur : il identifie les écarts exacts, les risques de télémétrie et les patterns à conserver comme références conceptuelles. |

---

## 5. Ce qui est exclu et la seule voie de réouverture

Cette décision exclut notamment :

- installer AO, ses paquets Go/Node/Electron ou son frontend;
- lancer son daemon, son serveur loopback, son SQLite, tmux/ConPTY ou son
  terminal sous contrôle d’ARENA;
- copier ses adapters, workers, migrations, GitHub/SCM observer, UI, API,
  configuration, clés PostHog/Sentry ou mécanismes cloud;
- synchroniser les branches, worktrees, PR, CI, reviews ou identifiants ARENA
  avec AO;
- accepter des commentaires GitHub, logs CI ou sorties AO comme instructions;
- ajouter une deuxième mémoire, un deuxième état de projet ou une deuxième
  autorité d’exécution;
- envoyer un contenu de dépôt privé à AO, à PostHog, Sentry, GitHub ou au cloud
  AO sans autorisation explicite du propriétaire.

Une réouverture ne peut viser **qu’une capacité nommée et manquante**, avec un
scénario utilisateur vérifiable. Elle doit alors :

1. commencer par l’adaptateur ARENA le plus petit, sous les interfaces
   existantes (`Atelier`, GitHub, reprise ou équipe), ARENA restant l’unique
   source de vérité;
2. rester local-first et sans télémétrie externe par défaut;
3. garder les branches/worktrees d’autrui intacts, ne jamais modifier `main`,
   ni fusionner ni supprimer un worktree sale;
4. traiter tout contenu de dépôt, agent, CI, PR et revue comme non fiable;
5. documenter licence, dépendances, credentials, réseau, test et mesure avant
   toute PR.

Une proposition raisonnable, **non implémentée**, serait un futur moniteur
GitHub ARENA strictement lecture seule et explicitement démarré par
l’utilisateur, si un besoin de suivi continu est établi. Il réutiliserait
`core/connectors/github.py`, les bornes de contenu et la frontière de confiance;
il ne lancerait pas AO et ne créerait pas un tableau de bord/daemon concurrent.

---

## 6. Licence, dépendances et limitations

AO est sous Apache-2.0, mais **aucune œuvre ni dépendance AO n’est utilisée**.
Il n’y a donc ni attribution de code tiers à ajouter, ni modification de
`THIRD_PARTY_NOTICES`, ni dépendance à résoudre.

Cet audit ne conclut pas qu’AO serait un mauvais produit; il conclut qu’il est
du mauvais format pour devenir une partie d’ARENA. Il ne mesure pas sa qualité
d’agent, ses performances, ses coûts, son comportement sur un dépôt privé, son
cloud privé ou l’exhaustivité de ses désactivations réseau en binaire empaqueté.
Ces éléments restent **UNKNOWN — non mesuré**.

La décision et sa frontière sont gardées par
`tests/test_agent_orchestrator_reste_une_reference.py`: aucune dépendance,
checkout ou import AO ne peut entrer silencieusement, et un worktree ARENA est
créé dans un vrai dépôt Git pour vérifier que la capacité locale qui fonde le
refus existe toujours.

---

## 7. Validation exécutée sur cette décision

| Commande | Résultat |
|---|---|
| `/tmp/arena-audit-venv/bin/python -m ruff check .` | **Passe** — `All checks passed!` |
| `/tmp/arena-audit-venv/bin/python -m pytest -q tests/test_agent_orchestrator_reste_une_reference.py tests/tools/test_atelier_worktree.py` | **Passe** — 14 tests, dont la frontière AO et le worktree réel |
| `/tmp/arena-audit-venv/bin/python -m pytest tests/ -q` | **Ne passe pas dans ce bac à sable :** 7 973 passés, 52 échecs, 61 ignorés, 61 désélectionnés. Les 52 échecs sont les chemins PDF/conversion/média qui exigent les binaires système absents `ffmpeg` et/ou `soffice` (LibreOffice); ils ne touchent pas ce changement documentaire ou son test. |

Le premier essai des commandes prescrites avec `/usr/bin/python` a été
**indisponible** (`No module named pytest` et `No module named ruff`). Une
venv temporaire hors dépôt a été créée avec les outils de développement et les
dépendances offline de la CI pour exécuter les commandes ci-dessus; elle n’est
ni suivie ni une dépendance d’ARENA.

Le résultat complet n’est donc pas présenté comme vert. Le travail ciblé passe,
mais la suite complète reste rouge tant que les binaires CI requis ne sont pas
installés dans ce bac à sable. Aucun résultat de performance AO/ARENA n’est
revendiqué.
