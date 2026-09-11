# Audit — Trans4mers (`abhayzangir1/trans4mer`)

*Mission ARENA x TRANS4MERS — reçue le 11/09/2026. Audit du code cloné, pas
du README.*

## Provenance

| | |
|---|---|
| Dépôt | `https://github.com/abhayzangir1/trans4mer` |
| Commit audité | `d0940a9` (`docs: remove Support the Developer section from README`) |
| Licence | MIT (`Copyright (c) 2026 Abhay Zangir`, `LICENSE` lu dans le clone) |
| Langage | Rust (workspace Cargo, 5 crates) + Tauri v2 + React/TypeScript (`apps/desktop`) |
| État | Alpha — `rust-version = "1.85"`, édition 2024, aucun tag de version stable trouvé |

**Traité comme un logiciel alpha non fiable par défaut** (mission §4) :
rien n'a été copié tel quel, chaque idée retenue a été réimplémentée dans le
style déjà en place d'ARENA (français, `Resultat`, aucune dépendance Rust).

## Architecture réelle (code lu, pas supposé)

Workspace : `core/trans4mers-domain` (modèles), `core/trans4mers-storage`
(SQLite + migrations), `core/trans4mers-engine` (41 modules — orchestration,
policy, approval, checkpoint, git, terminal, RAG, MCP, browser…),
`core/trans4mers-providers` (LLM/GitHub/browser/langfuse),
`core/trans4mers-app` (commandes Tauri), `apps/desktop` (React).

### Le mécanisme central étudié : anti-TOCTOU par hash d'arguments

`core/trans4mers-engine/src/approval_engine.rs` — `hash_arguments()` calcule
un SHA-256 sur une sérialisation JSON **canonique** (clés triées
récursivement, `canonical_arguments_json()`). `has_approved()` recalcule ce
hash **à partir des arguments qui vont réellement s'exécuter** et le compare
à ce qui a été approuvé (`(execution_id, tool_name, hash) -> Approved`,
`trans4mers_storage::repos::approval_repo`). Le point d'appel réel —
`agent_runtime.rs:1007`, dans la boucle ReAct, juste avant l'exécution de
l'outil — prouve que ce n'est pas une vérification à la demande d'approbation
seulement : **c'est l'exécution qui revérifie**, jamais une confiance
accordée une fois pour toutes. Une mutation des arguments entre l'approbation
et l'exécution produit un hash différent, donc `has_approved()` répond
`false`, et une NOUVELLE approbation est redemandée — c'est le mécanisme
anti-TOCTOU en entier, et il tient dans une comparaison de hash, pas une
architecture séparée.

### Ce qui l'entoure

- `domain/policy.rs` — treillis `Allow | Ask | Deny` (DENY gagne), avec
  `PolicyConditions{allowed_paths, blocked_paths, allowed_commands,
  blocked_commands}` par capacité/agent/projet.
- `domain/recovery.rs` — `FailureClass` à 4 valeurs (`State`, `Logic`,
  `Hallucination`, `Api`) et une `RecoveryPolicy` déterministe
  (`can_retry`, `max_retries`, `backoff_ms`, `requires_context_compaction`).
- `domain/execution.rs` — `AgentExecution.generation: u64` (« incremented on
  each resume — prevents stale events »), `Checkpoint.execution_phase`
  (`ContextAssembly | LlmGeneration | ToolExecution | WaitingForApproval |
  WaitingForMessage`), `ExecutionStep` avec **logging sémantique** (jamais la
  chaîne brute du modèle — un résumé structuré).
- `git_workspace.rs::ensure_git_workspace` — initialise un dépôt git si
  absent, et **protège `.trans4mers/` (ses worktrees isolés) par
  `.gitignore`** pour qu'un `git add -A` de l'arbre principal ne les aspire
  jamais.

## Ce qui a été FUSIONNÉ dans ARENA (DEC-0091)

Trois idées, chacune réimplémentée en Python sur les structures déjà en
place (`core/execution/reprise.py`, `tools/atelier/atelier.py`) — **rien du
code Rust n'a été copié**, la logique de chaque mécanisme a été relue puis
réécrite :

1. **État d'action « non confirmée »** (de `Checkpoint.execution_phase` /
   `ExecutionPhase::ToolExecution` + `WaitingForApproval`) → `Etape.
   confirmee` dans `core/execution/reprise.py`, avec `amorcer()`/
   `confirmer()` encadrant chaque action de `DioumtoukayAgent`.
2. **Concurrence sans confirmation d'aucune sorte** — trans4mer sérialise via
   sa base SQLite et son `PolicyOutcome`. ARENA n'a ni SQLite partagé sur ce
   chemin ni confirmation possible (DEC-0038) : un **verrou mémoire par
   chemin canonique** (`tools/atelier/verrous.py`) a été écrit à la place,
   granularité FICHIER seulement (mission §21, « use only what's needed »).
3. **Isolation par worktree git** (`git_workspace.rs`) → `Atelier.isoler()`/
   `nettoyer_worktree()`, `git worktree add`/`remove` en shell nu (comme le
   reste du module), avec la même protection `.gitignore`.

## Ce qui a été délibérément REJETÉ, et pourquoi

- **Le hash d'approbation lui-même (anti-TOCTOU au sens strict de la
  mission, §11/§45)** : son objet chez trans4mer est de vérifier qu'un
  humain approuve EXACTEMENT ce qui va s'exécuter. **`DioumtoukayAgent` n'a
  pas d'étape d'approbation humaine** — DEC-0038, la décision explicite et
  documentée du propriétaire (« il doit tout faire pas de limite »), lue
  intégralement avant d'écrire une ligne de cette mission. Ajouter une
  vérification d'approbation là où aucune approbation n'existe reviendrait
  à réintroduire, par un autre nom, exactement la garde-fou que DEC-0038
  retire en connaissance de cause. **Non re-litigé.** Ce que la concurrence
  RÉELLE (deux tâches, aucune approbation) demandait — ne jamais laisser
  deux écritures s'entrelacer — est couvert par le verrou par fichier
  ci-dessus, qui protège sans jamais rien approuver ni refuser.
- **Le bac à sable de chemins / le treillis `allowed_paths`/`blocked_paths`**
  (§34) : `Atelier` suit délibérément un chemin absolu hors de sa racine —
  « ce n'est pas une prison », DEC-0038 à nouveau, cité dans le docstring du
  module lui-même depuis le 02/09/2026. Une jaugeolette de chemins autorisés
  irait directement contre cette décision.
- **CQRS / event sourcing complet, `cqrs.rs`, `event_bus.rs`,
  `event_projector.rs`** : ARENA a déjà un journal durable écrit après
  chaque étape (DEC-0072) — étendu ici en écriture AVANT (`amorcer`).
  Reconstruire un bus d'événements/projecteur par-dessus n'ajouterait rien
  qu'`amorcer()`/`confirmer()` ne couvre déjà pour le seul besoin réel
  mesuré (une étape à l'état inconnu après un arrêt brutal).
- **PTY réel (`terminal_manager.rs`, `portable-pty`)** : `Atelier.executer()`
  utilise déjà `subprocess.Popen` avec capture stdout/stderr fidèle et code
  de sortie réel — suffisant pour tout ce que Dioumtoukay lance aujourd'hui
  (pas de REPL interactif, pas de serveur de dev à piloter en direct). Une
  vraie PTY ajouterait une dépendance pour un besoin non mesuré ici — mission
  §30, « if not needed, do not add complexity ».
- **Navigateur (`browser_space_manager.rs`, CDP), mémoire à
  paliers (`memory_engine.rs`, `memory_tier_promoter.rs`), RAG hybride
  (`document_rag.rs`, `bm25.rs`), MCP (`mcp_server_bridge.rs`)** : ARENA a
  déjà chacune de ces capacités par une mission dédiée et auditée — Fuji-Web
  (DEC-0079), AI Memory Vault (DEC-0090), txtai (DEC-0051), `core/mcp/`
  (deux transports, DEC-0072/0077 l'ont déjà vérifié). **Aucune n'a été
  touchée ici** : les dupliquer aurait été exactement ce que la mission
  interdit en toutes lettres (§2, §36-39).
- **Multi-agent temps réel / swarm (`swarm_orchestrator.rs`,
  `delegate_task.rs`)** : Dioumtoukay reste un agent unique qui AGIT — DEC-0063
  a déjà tranché que les trois autres rôles (`RepoEngineerAgent`, `SWEAgent`,
  `CoderAgent`) restent des spécialistes consultés, jamais une armée
  d'agents concurrents. Non re-litigé.

## Ce que ça coûte si c'est faux

Le verrou par fichier (`tools/atelier/verrous.py`) est un mutex **en
mémoire du processus** : il protège contre deux tâches concurrentes dans le
MÊME processus `apps/backend`, pas contre deux processus ARENA distincts
écrivant le même fichier (scénario qui n'existe pas aujourd'hui — un seul
processus backend est lancé). S'il venait à exister, cette protection ne
s'appliquerait plus et devrait être refaite au niveau du fichier disque
(verrou `fcntl`/`flock`), pas simplement réutilisée. L'amorce/confirmation
(`core/execution/reprise.py`) suppose que le journal JSON reste lisible
après un crash — un disque plein PENDANT l'écriture de l'amorce laisserait,
au pire, l'ancien comportement (rien écrit), jamais un état pire que sans
cette mission.
