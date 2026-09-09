# Audit — Cline (`cline/cline`) et la boucle de codage d'ARENA

**Date** : 09/09/2026
**Mission** : intégrer les capacités de Cline utiles à l'agent de codage
existant (Dioumtoukay / Usman Coder) — jamais un second agent de codage.

## 1. Ce qu'est Cline aujourd'hui, mesuré, pas supposé

Cloné frais : `https://github.com/cline/cline`, HEAD `fee4fb96f2c946a54d4f083ee
bba6b6b4b73cf9b` (09/09/2026), licence **Apache-2.0** (`LICENSE` présent,
en-tête standard).

Ce n'est plus « une extension VS Code » : c'est un monorepo Bun
(`@cline/packages`) avec `sdk/packages/{agents,core,llms,sdk,shared,ui}` et
`apps/{cli,cline-hub,examples,vscode,vscode-rollout}`. `sdk/packages/core/src/`
contient, entre autres : `account/`, `auth/` (WorkOS, device-auth d'équipe),
`cron/` (un ordonnanceur complet — événements, rapports, planification),
`hub/` (démon client/serveur/discovery), `session/team/` (partage de session
entre plusieurs personnes), `remote-config/`, `telemetry/`, et
`runtime/{capabilities,config,host,orchestration,safety,tools,turn-queue}`.

**Constat structurel, avant même de lire une ligne de logique** : la majorité
de ce périmètre répond à un besoin qu'ARENA n'a pas — un outil d'équipe,
multi-utilisateur, avec compte cloud, ordonnanceur intégré et démon de fond.
ARENA est un assistant personnel, un seul propriétaire, un seul processus
FastAPI. `cron/`, `hub/`, `session/team/`, `auth/` (WorkOS), `remote-config/`,
`telemetry/` sont donc écartés au niveau structurel — même règle que pour
Open SWE, File_Converter_Pro, AI File Sorter et PDFx : le second
ordonnanceur, le second système de comptes ou le second serveur ne sont
jamais demandés, et ARENA en a déjà (`core/execution/travaux.py`,
`core/execution/coordination.py`).

Trois zones ont été lues en détail, parce qu'elles sont la seule partie du
dépôt qui touche exactement ce que fait Dioumtoukay — exécuter une action,
la faire approuver, savoir s'arrêter :

- `sdk/packages/core/src/runtime/tools/tool-approval.ts` (variante
  « Desktop ») ;
- `sdk/packages/core/src/runtime/safety/loop-detection.ts` ;
- `sdk/packages/core/src/runtime/safety/mistake-tracker.ts`.

`sdk/packages/agents/`, `sdk/packages/llms/`, `extensions/mcp/`, `apps/cli/`
n'ont été audités qu'au niveau de leur structure (listing), pas ligne à
ligne : la matrice §3 en donne la raison ligne par ligne — dans chaque cas,
ARENA a déjà l'équivalent, mesuré dans des missions antérieures, et rouvrir
un composant qui marche « pour être sûr » est exactement ce que
`PROJECT_MEMORY/ACTIVE_WORK.md` interdit.

### `tool-approval.ts` — REJETÉ, ARENA a déjà mieux

C'est un pont de fichiers : le processus agent écrit une requête JSON,
attend qu'un fichier `.decision.json` apparaisse (poll toutes les 200 ms,
timeout 5 min), pour relier un processus headless à une UI Desktop
(VS Code). ARENA n'a pas ce problème : la confirmation vit dans le même
processus FastAPI, via `core/actions/attente.py` (confirmer deux fois
n'exécute qu'une fois) et `/api/actions/pending|confirm|cancel` —
déjà persistée, déjà couverte par la politique de permissions à deux
couches. Le mécanisme de Cline est une solution à un problème
d'architecture (deux processus séparés) qu'ARENA n'a pas.

### `loop-detection.ts` et `mistake-tracker.ts` — l'idée retenue

Deux gardes, distinctes de celles déjà dans `dioumtoukay_agent.py`
(DEC-0063 : `DUREE_MAX_SECONDES`, `ILLISIBLES_CONSECUTIVES_MAX`) :

- **`checkRepeatedToolCall`** compare la signature (nom + arguments
  normalisés) d'un appel d'outil à la précédente ; au-delà d'un seuil,
  arrête AVANT de rejouer l'appel identique.
- **`MistakeTracker.record`** compte les échecs D'EXÉCUTION consécutifs
  (pas les réponses illisibles — des appels bien formés qui échouent
  quand même), et arrête au-delà d'un seuil.

Aucune ligne copiée : la classe `LoopDetectionTracker`/`MistakeTracker`
(canal d'événements typé, hooks `beforeTool`, notices de récupération
injectées dans le prompt) appartient à l'architecture TypeScript de Cline —
elle n'a pas de sens en Python sur la boucle à une action par tour de
Dioumtoukay. Ce qui est repris, c'est le **principe** des deux compteurs, et
il a été réécrit natif, au même niveau que les deux gardes DEC-0063 déjà en
place.

## 2. Ce qu'ARENA avait déjà, mesuré avant tout code

| Composant | État mesuré |
|---|---|
| `agents/dioumtoukay/dioumtoukay_agent.py` | 905 lignes, boucle une-action-par-tour, `TOURS_MAX=12`, `DUREE_MAX_SECONDES=20min`, `ILLISIBLES_CONSECUTIVES_MAX=3` (DEC-0063). **Aucune garde anti-répétition, aucune garde anti-échecs-répétés.** |
| `tools/atelier/atelier.py` | 488 lignes — `lire`/`ecrire`/`remplacer`/`chercher`/`lister`/`deplacer`/`copier`/`supprimer`/`creer_dossier`/`metadonnees`/`executer`/`git`. Sans garde-fou (DEC-0038, décision du propriétaire, ne pas rouvrir). |
| `core/mcp/transport.py` + `stdio_transport.py` | 213 + 297 lignes — client MCP réel (streamable-HTTP et stdio), déjà utilisé par 2 connecteurs réels (`opentakeoff.py`, `wan2gp.py`). **ARENA a déjà MCP.** |
| Permissions/confirmation | `core/permissions/{politique,controle}.py` (2 couches, la plus stricte gagne) + `core/actions/attente.py` (confirmer 2× n'exécute qu'1×). |
| Git/GitHub | `Atelier.git` (shell nu) + `core/connectors/github.py` (DEC-0073) — PR toujours `draft`, `CONFIRMATION`. |
| Modèles | `core/models/*`, routage hybride par sensibilité (DEC-0009/0021/0022) — bien plus riche que ce que Cline propose pour un usage mono-utilisateur. |
| Tâches de fond | `core/execution/travaux.py` (`FileDeTravaux`), reprise de tâche (`core/execution/reprise.py`, `JournalDeReprise`). |

## 3. Matrice de comparaison (20 lignes)

| Capacité | Décision | Pourquoi |
|---|---|---|
| Filesystem | KEEP ARENA | `Atelier` couvre lire/écrire/chercher/déplacer/copier/supprimer, DEC-0038 assumé |
| Terminal | KEEP ARENA | `Atelier.executer` : liste d'arguments, timeout réel, kill de groupe de processus |
| Recherche de code | KEEP ARENA | `Atelier.chercher` (grep + repli Python pur) |
| Gestion du contexte | KEEP ARENA | RAG existant (LightRAG/GraphRAG, `core/memory/*`) — aucun second RAG |
| Planification | KEEP ARENA | `RepoEngineerAgent`/`SWEAgent` consultés via `_consulter()` |
| État de tâche | KEEP ARENA | `JournalDeReprise` — reprise déjà posée (DEC-0072) |
| Checkpoints | NOT NEEDED | Snapshots pour rembobiner une UI Desktop — ARENA n'a pas d'UI de ce type, git suffit |
| MCP | KEEP ARENA | `core/mcp/transport.py`+`stdio_transport.py`, déjà utilisé réellement, rien à améliorer trouvé |
| Git | KEEP ARENA | `Atelier.git` |
| GitHub | KEEP ARENA | `core/connectors/github.py` (DEC-0073) |
| Sandbox | KEEP ARENA (décision propriétaire) | DEC-0038 : aucun garde-fou dans `Atelier`, en connaissance de cause |
| Sous-processus | KEEP ARENA | même mécanisme que Terminal |
| **Récupération d'erreur** | **ADAPT CLINE IDEA** | deux gardes manquantes : répétition de la même action, échecs d'exécution consécutifs — voir §1 |
| Abstraction modèle | KEEP ARENA | routage hybride par sensibilité, plus riche que le besoin |
| Streaming | NOT NEEDED ici | une action par tour est un choix délibéré (style mini-swe-agent) ; le streaming existe ailleurs (`/api/chat/stream`) |
| Tâches longues | KEEP ARENA | `core/execution/travaux.py` |
| Exécution de fond | KEEP ARENA | idem, annulation réelle vérifiée en mission antérieure |
| Confirmation humaine | KEEP ARENA (Cline rejeté) | `core/actions/attente.py` déjà plus robuste que le pont fichiers de Cline — voir §1 |
| Sécurité | KEEP ARENA | `core/security/trust.py`, permissions à 2 couches, DEC-0038 documenté |
| Observabilité | KEEP ARENA | `JournalDesActions`, `/api/actions`, `/api/observability` |

**19 lignes sur 20 : garder ce qui existe.** Une seule adaptation retenue.
C'est le même résultat que pour Open SWE, File_Converter_Pro, AI File Sorter
et PDFx : le composant qui manquait était petit, précis, et le reste du
projet externe ne s'applique pas à l'architecture d'ARENA.

## 4. Ce qui a été construit

`agents/dioumtoukay/dioumtoukay_agent.py` :

- `ACTIONS_IDENTIQUES_CONSECUTIVES_MAX = 3` — `Action.signature()` (nom +
  champs triés + blocs triés) comparée au tour précédent ; au 3ᵉ appel
  identique d'affilée, la boucle s'arrête **avant** de le rejouer.
- `ECHECS_CONSECUTIFS_MAX = 3` — un compteur d'échecs d'exécution
  (`resultat.ok is False`) consécutifs, remis à zéro au premier succès ;
  au 3ᵉ échec d'affilée, la boucle s'arrête, la dernière tentative restant
  dans le rendu (rien n'est caché).

Les deux gardes sont indépendantes de `ILLISIBLES_CONSECUTIVES_MAX` (une
réponse illisible n'est ni une action répétée, ni un échec d'exécution) et
de `DUREE_MAX_SECONDES`/`TOURS_MAX` (elles arrêtent plus tôt un travail qui
ne progresse pas, sans attendre le plafond de temps ou de tours).

## 5. Un vrai defaut trouvé en construisant

Le test existant `TestIlDitLaVerite::test_il_s_arrete` rejouait
délibérément la MÊME action `TOURS_MAX + 5` fois pour vérifier le plafond
`TOURS_MAX`. Avec la nouvelle garde anti-répétition, ce scénario s'arrête
désormais après 2 exécutions (au lieu de 12) — la garde anti-répétition
intercepte avant `TOURS_MAX`. Ce n'est pas une régression du comportement
(l'agent s'arrête plus tôt, ce qui est l'objectif), mais le test ne visait
plus ce qu'il prétendait viser. Corrigé : le test alterne désormais deux
actions différentes, pour que ce soit bien `TOURS_MAX`, et seulement lui,
qui l'arrête.

## 6. Ce qui n'a délibérément PAS été intégré, et pourquoi

- **`cron/`, `hub/`, `session/team/`, `auth/` (WorkOS), `remote-config/`,
  `telemetry/`** : machinerie multi-utilisateur/plateforme, aucun besoin
  correspondant chez un assistant personnel mono-processus.
- **`tool-approval.ts`** : pont IPC par fichiers pour relier deux
  processus séparés (agent headless + UI Desktop) — `core/actions/attente.py`
  résout déjà ce problème, dans un seul processus, de façon plus robuste.
- **`sdk/packages/agents/`, `sdk/packages/llms/`, `extensions/mcp/`,
  `apps/cli/`** : non lus ligne à ligne. La matrice §3 montre qu'ARENA a
  déjà, mesuré, l'équivalent de chacun (Atelier, routage de modèles,
  `core/mcp/`, boucle Dioumtoukay elle-même comme surface headless) — les
  rouvrir « pour être sûr » est exactement ce que la mémoire opérationnelle
  du projet interdit.
- **Le système de checkpoints/snapshots** : conçu pour rembobiner une
  session dans une UI Desktop ; ARENA n'a pas cette UI, et git fait déjà ce
  travail pour un dépôt suivi.

## 6bis. Vérification : suite complète, et un défaut trouvé au passage

`44/44` tests dédiés à Dioumtoukay passent, sabotage compris (les deux
conditions désactivées une à une font échouer exactement leurs deux tests,
et seulement eux — voir §4/§5).

La suite complète (`pytest tests/`) a été tentée quatre fois pour confirmer
l'absence de régression ailleurs. Les trois premières fois, elle progresse
sans un seul échec jusqu'à 57-58 %, puis se bloque — jamais un échec, un
blocage d'E/S réel (état processus `D`, insensible à tout délai
d'expiration, y compris 120 s). Isolé avec `-v` : le blocage est dans
`tests/agents/test_repo_engineer.py` (famille `TestLeRegardSurLeDepotVient
DeGitingest`), qui exerce `gitingest` sur le dépôt réel — très probablement
la marche dans le SDK Faceplugin vendoré (1,2 Go, `tools/vision/
faceplugin/.../.venv/`), déjà connu pour bloquer un parcours non protégé
(`scripts/orphelins.py` et `tests/test_connecteurs_dormants.py` l'excluent
explicitement via `MOTEURS_EXTERNES` — `RepoEngineerAgent`/`gitingest` ne
l'exclut pas).

**Sans aucun rapport avec cette mission** : ni `agents/dioumtoukay/`, ni
`tools/atelier/`, ni les gardes ajoutées ici ne touchent `gitingest` ou
`RepoEngineerAgent`. Non corrigé — hors périmètre de DEC-0077. Deux autres
défauts pré-existants, sans rapport non plus, ont été trouvés et nommés en
chemin : `tests/core/test_connecteur_file_conversion.py::TestSecuriteChemin
::test_meme_format_source_et_cible_est_un_echec` (bloque sur un appel
LibreOffice réel alors que le test attend un court-circuit avant tout
moteur) et `tests/test_doctor.py::test_le_rapport_survit_a_n_importe_quelle
_sonde_qui_leve` (bloque sur le pont subprocess du connecteur Faceplugin).
Les trois sont reproductibles en isolation, indépendamment les uns des
autres et de cette mission.

**Preuve retenue, proportionnée à l'ampleur du changement** (deux
constantes et une comparaison inline dans un seul fichier) : 44/44 tests
dédiés + sabotage, plus 57-58 % de la suite complète traversés sans un
seul échec à trois reprises avant chaque blocage pré-existant.

## 7. Licence et provenance

Cline est Apache-2.0. Aucune ligne de code TypeScript n'a été copiée : les
deux constantes et leur logique (comparaison de signature, compteur remis à
zéro) sont une réimplémentation native en Python, au même niveau
d'abstraction que les gardes DEC-0063 déjà citées comme inspirées de
mini-SWE-agent dans ce même fichier — le commit exact (`fee4fb9`) et les
deux fichiers sources sont cités dans les docstrings des constantes, pour
que la provenance reste traçable sans qu'aucune ligne ne soit partagée.
