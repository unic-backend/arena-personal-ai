# PHASE 0 — Audit du dépôt avant toute modification

*12/09/2026. Commit audité : `148c9bf` (`main`). Aucune ligne de code modifiée
pendant cet audit.*

**Méthode.** Rien n'est déclaré d'après un nom de fichier. Chaque ligne de ce
rapport vient soit d'une sonde exécutée sur le vrai code, soit d'une lecture
d'AST du chemin d'exécution réel. Les commandes sont reproductibles et citées.

---

## Surface mesurée

```
modules python (hors tests et moteurs tiers) : 311
fichiers de test                             :  287
agents                                       :   25
connecteurs                                  :   44
routeurs FastAPI                             :   16
intentions de chat                           :   27
```

`python scripts/orphelins.py` → **300 modules, 240 atteints, 60 orphelins**, et
`orphelins_reels()` → **0**. Les 60 sont des `__init__`, des scripts lancés en
sous-processus ou des services lancés par le propriétaire. **Aucun module mort
au sens de l'import.**

Mais « module atteint » n'est pas « capacité atteignable depuis une phrase ».
C'est la distinction que le reste de cet audit mesure.

---

## A. La porte des intentions — LIVE

Sonde : lecture d'AST de `dispatch_request` (`apps/backend/routers/chat.py`)
comparée à `AGENTS_SPECIALISES` (`apps/backend/config.py`).

```
AGENTS_SPECIALISES (la porte)        : 27 intentions
Intentions vues dans dispatch_request: 27
Dans la porte mais non traitées      : aucune
Traitées mais absentes de la porte   : aucune
```

**La symétrie est exacte.** Et chacune des 27 branches contient un appel réel —
aucune branche vide, aucun `pass` :

| INTENTION | APPEL RÉEL DANS SA BRANCHE |
|---|---|
| ARCHITECTURE_3D | `executer_architecture` |
| ATELIER | `dioumtoukay_agent.run` |
| AUDIO | `audio_agent.run`, `medias_montables` |
| BROWSER | `browser_agent.run` |
| CODE_EXECUTION | `coder_agent.run` |
| DEEP_REASONING | `reasoning_engine.solve_complex_task` |
| DEEP_RESEARCH | `researcher_agent.run` |
| DESIGN_UI | `registre.executer` |
| EMAIL | `email_agent.run` |
| EXECUTIVE | `executive_agent.run` |
| FINANCE | `finance_agent.run` |
| FRESH_INFO | `_donnees_senegal`, `fresh_agent.run` |
| GRAPHRAG | `graphrag_tool.query_global` |
| MONTAGE | `montage_agent.run` |
| PLAQUISTE | `plaquiste_agent.run` |
| PREUVE_FORMELLE | `formel_agent.run` |
| RAG_DOCS | `lightrag_tool.query`, `indexer_ses_documents` |
| REPO_ENGINEERING | `repo_engineer.run` |
| SOCIAL | `social_agent.run` |
| STUDIO | `lancer_studio` |
| SWE_FIX | `swe_agent.run` |
| TREND_SEARCH | `trend_agent.run` |
| UI_GENERATE | `ui_agent.run` |
| VIDEO_ANALYSIS | `video_agent.run`, `validate_media_path` |
| VIDEO_PROJET | `video_production_agent.run` |
| VISAGE | `_analyse_de_visages` |
| VISION | `vision_agent.run` |

**STATUS : LIVE.** **ACTION : aucune.** Ne pas « refactoriser » cette porte :
c'est elle qui rend les agents atteignables, et sa symétrie est testée.

---

## B. Permissions et bac à sable — LIVE, et vérifié par sabotage

`core/connectors/base.py::_conduire` applique, **dans cet ordre** : capacité
déclarée → **permission** → santé → quota → crochets → exécution. La permission
passe avant tout, et un refus ne révèle même pas si le service est joignable.
`executer_confirmee()` est une **méthode distincte** et non un argument
`confirmation=True` — un argument voyagerait dans les `**parametres` d'un
appelant quelconque et contournerait la confirmation.

**Le point que la mission signale comme critique (EXECUTE_COMMANDS), mesuré.**
Sabotage : le démon Docker ne répond plus.

```
docker_available : False   image_disponible : False

execute_python_code("import os; print(os.listdir('/'))") rend :
   success      = False
   refused      = True
   exit_code    = -1
   stdout       = (vide)
   sandbox_mode = REFUSED
   error        = « Exécution refusée par sécurité : le démon Docker est inactif. »
```

**Le code n'a pas été exécuté.** Pas de repli silencieux sur l'hôte. Le repli
existe mais exige `ALLOW_UNSAFE_EXEC=true`, absent de l'environnement.

**STATUS : LIVE.** **ACTION : aucune sur le mécanisme.** La Phase 10 de la
mission demande de vérifier que `permission → authorization → sandbox →
execution` est respecté : **il l'est**, et c'est prouvé, pas supposé.

---

## C. Frontière donnée / consigne sur le web — PARTIAL, un trou réel

`core/security/trust.py` définit `TrustLevel.EXTERNAL` (« web, dépôt tiers, API
tierce — hostile par défaut ») et `wrap()`. Sonde sur les quatre chemins qui
ramènent du web :

| Chemin | Enveloppe le contenu externe ? |
|---|---|
| `agents/fresh_info/fresh_info_agent.py` | **OUI** |
| `agents/trend_analyzer/trend_analyzer_agent.py` | **OUI** |
| `core/executive/specialistes.py` | **OUI** |
| `agents/executive/executive_agent.py` | **NON** |
| `tools/search/web_search_tool.py` | **NON** |

**PROBLÈME.** `ExecutiveAgent` — précisément la couche que la Phase 2 veut
promouvoir au centre — appelle la recherche web et remet les résultats au
modèle **sans les marquer comme externes**. Le trou n'est pas théorique : c'est
le chemin par lequel une page web pourrait parler au modèle sur le même ton
qu'une consigne système.

**STATUS : PARTIAL. ACTION (P0, avant toute promotion de l'Executive) :**
envelopper à la source, dans `WebSearchTool`, plutôt qu'à chaque appelant — un
appelant qui oublie est exactement ce qui vient d'être mesuré.

---

## D. Boucle agentique — **ABSENTE**, c'est le vrai manque

`ReasoningEngine.solve_complex_task` est une `Coordination` de **trois étapes
fixes** : `plan` → `calcul` (facultative) → `synthese`. Chaque étape a des
essais (`essais_max`), des dépendances (`depend_de`) et une vérification
(`verifier=_non_vide`, `_calcul_reussi`).

Ce qui existe donc : **le retry, la dépendance, la vérification de non-vacuité,
la tolérance à un bac à sable absent.** Ce qui n'existe pas : **la
replanification.** Le plan est produit une fois et n'est jamais révisé après
observation. Sonde sur tout `core/` et `agents/` :

```
"replan"          : 1 fichier  (agents/plaquiste/metre_plan.py — sans rapport)
"nouveau plan"    : 0 fichier
"ajuster le plan" : 0 fichier
max_steps/max_etapes : 2 fichiers (browser_agent, connecteur browser)
```

**STATUS : PARTIAL (pipeline fixe) / le replan est DEAD (inexistant).**
**ACTION : c'est le cœur du travail à faire (Phase 3).** La bonne nouvelle :
`Coordination` fournit déjà l'état explicite en Python que la mission exige
(« ne jamais simuler la boucle dans du texte généré »). Le replan s'y greffe,
il ne demande pas de tout réécrire.

---

## E. Model Router — LIVE, et déjà fondé sur la confidentialité

`core/models/routeur.py` classe **d'abord** la confidentialité
(`core/models/confidentialite.py::classer`, `cloud_autorise`) : « sans réseau,
sans clé, budget atteint, **ou texte sensible** : Ollama ». Le `Choix` porte
`confidentialite.niveau`. Le plafond cloud est réservé avant l'appel
(`_reserver_si_cloud`), ce qui tient sous concurrence.

Ce qui **manque** au regard de la Phase 8 : le routeur ne tient **aucune
statistique de qualité par type de tâche** (`success_rate`, `latency`, `cost`
existent partiellement ; `quality` et `task_type` non).

**STATUS : LIVE. ACTION (P1) :** ajouter l'apprentissage par type de tâche.
**Ne pas réécrire le classement de confidentialité** : c'est la garantie
centrale, et elle est testée.

---

## F. Mémoire — LIVE, et réparée aujourd'hui même

Trois défauts mesurés et corrigés le 12/09 (PR #202, #203, #204, fusionnées) :
relecture chiffrée 2 min 14 → 3,6 ms ; un souvenir sensible était introuvable
par mot-clé ; chaque lecture construisait un TEMP B-TREE (20,56 → 5,05 ms).

Au regard de la Phase 4, ce qui **existe** : `FACT / PREFERENCE / INFERENCE /
CONTEXTE_TEMPORAIRE`, l'importance, l'état (`ACTIF/REJETE/ARCHIVE`), le
chiffrement au repos, la provenance (`source` obligatoire), et la règle « une
inférence ne devient pas un fait toute seule » — **testée nommément**
(`test_une_inference_ne_devient_pas_un_fait_toute_seule`).

Ce qui **n'existe pas** : `EPISODE`, `DECISION`, `PROCEDURE`, `MISTAKE`, la
`confidence`, le `source_count`, la validité temporelle, et **la détection de
contradiction**.

**STATUS : LIVE pour ce qu'elle couvre, les 4 types manquants sont ABSENTS.**
**ACTION (P1) :** ajouter les types, pas réécrire. `core/memory/personnelle.py`
est **zone verrouillée** (schéma + migration qui n'efface rien) : toute
extension passe par `ALTER TABLE`/table annexe, jamais par une réécriture.

---

## G. Observabilité — PARTIAL

`GET /api/observability` existe et un travail est suivable de bout en bout
(`/observability/trail/{id}`). Le journal des actions masque les secrets
(`core/actions/journal.py`, zone verrouillée).

Ce qui **manque** au regard de la Phase 13 : pas de `request_id` unifié
traversant toute la chaîne, pas de `plan_id`, pas de `memory_hits`, pas de
`stop_reason`, pas de `verification_used`.

**STATUS : PARTIAL. ACTION (P1)**, à faire **en même temps** que la boucle
agentique : ces champs n'ont de sens que s'il y a un plan à identifier.

---

## H. Ce que cet audit n'a PAS mesuré

Dit franchement plutôt que passé sous silence. Les axes suivants n'ont été vus
qu'au niveau existence/appel, sans sonde d'exécution :

- vision, voix, vidéo, RAG documentaire — `doctor.py` les rapporte tous
  `[CONF]`/`[ABS]` sur cette machine (aucun modèle, pas de GPU, services
  externes absents), donc aucune exécution réelle n'est mesurable ici ;
- la surface API détaillée (16 routeurs), au-delà de `/api/memory` ;
- Docker / déploiement au-delà du fait que l'image se construit en CI.

**Ces mesures exigent la machine du propriétaire.** Les annoncer comme faites
ici serait exactement ce que la mission interdit.

---

## Priorités, telles que la mesure les ordonne

| # | Travail | Pourquoi cet ordre |
|---|---|---|
| **P0** | envelopper le web à la source (`WebSearchTool`) | trou de sécurité réel, sur la couche qu'on veut promouvoir |
| **P0** | boucle agentique avec replan, greffée sur `Coordination` | le seul manque structurel ; tout le reste existe |
| **P0** | budgets explicites (`max_steps`, `max_time`, `max_tokens`, `max_tool_calls`) | sans eux, une boucle qui replanifie ne s'arrête pas |
| **P1** | types de mémoire manquants + contradiction | additif, zone verrouillée respectée |
| **P1** | `request_id`/`plan_id` de bout en bout | n'a de sens qu'avec un plan |
| **P1** | statistiques du routeur par type de tâche | optimisation, pas correction |
| **P2** | benchmark local des modèles | exige sa machine |

**Ce qu'il ne faut PAS toucher** : la porte des intentions, l'ordre des
contrôles de `base.py`, le classement de confidentialité, le schéma de la
mémoire personnelle. Les quatre sont vivants, testés, et deux sont des zones
verrouillées.
