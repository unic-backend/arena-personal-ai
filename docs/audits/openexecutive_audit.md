# Audit — OpenExecutive (mission ARENA x OPENEXECUTIVE, DEC-0086)

## Provenance

- **Dépôt** : `SenteLabsAI/OpenExecutive`
- **Commit audité** : `fc72987537069173cb6402a1892bc03fd74f5454` (2026-09-10)
- **Licence du dépôt** : Apache-2.0 (fichier `LICENSE` vérifié, pas seulement le badge du README)
- **Licence des poids/modèles** : sans objet — OpenExecutive n'entraîne ni ne distribue de
  poids ; il appelle l'API Claude d'Anthropic et, en configuration, OpenRouter.

Aucun code d'OpenExecutive n'est vendoré ici. Ce document enregistre ce qui a été **compris**
et **comparé**, pas copié.

## Ce que le dépôt fait réellement (vérifié dans le code, pas dans le README seul)

| Domaine | Fichier(s) | Constat |
|---|---|---|
| Orchestration | `orchestrator/executive.py`, `orchestrator/router.py` | Une Executive persona LLM (Claude) décide, via un tool `consult_specialist`, quel(s) spécialiste(s) consulter — **jamais un routage codé en dur** |
| Parallélisme | `orchestrator/router.py::route_parallel` | `asyncio.gather` sur les appels spécialistes ; chaque spécialiste reçoit son propre contexte RAG filtré par domaine ; un plafond de fan-out (`resolve_fanout_cap`) protège d'un tour qui consulterait tout le monde |
| Spécialistes | `agents/*.py` | 10 agents (`cso`, `cfo`, `chro`, `gc`, `coo`, `cmo`, `cpo`, `board_comms`, `talent`, `triage`) — chacun un simple prompt de persona + modèle, **aucun calcul déterministe** |
| Révision | `orchestrator/committee.py` | Un « Comité » : 1 juge qualité + 2 réviseurs de domaine (repli sur `cso`+`cfo` si moins de deux spécialistes consultés), critique le brouillon en parallèle, une seule passe de révision — c'est une relecture adversariale du texte, **pas** une préservation structurée du désaccord entre spécialistes |
| Mémoire | `memory/episodic.py`, `memory/decision_ledger.py` | SQLite ; extraction des décisions par un modèle léger (Haiku) en tâche de fond ; `decision_ledger.py` ajoute un cycle proposé→exécuté/approuvé/rejeté/annulé avec agrégation de fiabilité (Build 3, autonomie progressive) |
| RAG | `knowledge/retriever.py`, `knowledge/store.py` | ChromaDB local, deux collections (`builtin_knowledge` MBA + `company_docs`), filtrage par domaine par spécialiste (`DOMAIN_ALIASES`) |
| Autorité | `departments/authority.py` | Une « porte d'autorité » à 3 issues (`execute` / `propose` / `escalate`) selon le niveau d'autonomie du département — un mécanisme de permission progressive, pas un tout-ou-rien |
| Fournisseurs | `providers/anthropic_provider.py`, `providers/openrouter_provider.py`, `providers/openai_compatible.py` | Le code supporte plusieurs fournisseurs ; le README et `docs/architecture.md` ne présentent que Claude comme « backbone » — **l'indépendance modèle existe dans le code, elle n'est pas mise en avant dans la doc** |
| Intégrations | `integrations/{slack,discord,telegram,google_chat,email_poller}.py` | Chaque intégration applique un contrôle d'accès par roster (`Person` non archivée) avant de répondre |
| Évaluation | `evals/` | 29 scénarios, notés par `claude-opus-4-7` en LLM-as-judge sur 5 dimensions (persona, exactitude domaine, usage du contexte, qualité du routage, actionnabilité) ; seuil CI : moyenne ≥ 3,5/5, aucune dimension ne doit chuter de >10 % vs `main` |
| Sécurité | `SECURITY.md`, `integrations/response_gate.py`, `orchestrator/outbound_guard.py` | Espace de travail partagé, tous les utilisateurs autorisés sont traités comme fiables (pas d'isolation par utilisateur) ; l'injection de prompt menant à une action sortante non voulue est explicitement dans le périmètre de signalement |

## Ce qui n'a PAS pu être confirmé, ou est plus faible qu'annoncé

- **« Structured Output »** : contrairement à AutoHedge (audité dans une mission antérieure
  d'ARENA), les agents d'OpenExecutive ne déclarent aucun schéma structuré — chaque
  spécialiste rend une chaîne de texte libre. La distinction FAIT/CALCUL/HYPOTHÈSE que la
  mission actuelle demande (§9) **n'existe pas** dans OpenExecutive.
- **Calcul déterministe** : aucun. Marge, trésorerie, faisabilité de délai — tout est laissé
  à l'interprétation du modèle. C'est exactement le défaut qu'ARENA a déjà corrigé pour la
  finance de marché (`core/finance/`, audit AutoHedge) et que cette mission corrige pour la
  finance d'affaires (`core/executive/calcul_affaires.py`).
- **Désaccord préservé** : le Comité *révise* un brouillon déjà unifié — il ne fait jamais
  cohabiter deux conclusions opposées dans la sortie finale. La mission actuelle (§8) exige
  l'inverse : le désaccord doit survivre à la synthèse.
- **Une seule voix, jamais montrée à l'utilisateur** : le choix architectural d'OpenExecutive
  ("The internal agent architecture is never exposed") est délibérément **rejeté** ici —
  la mission (§29/§38) demande une trace de QUI a conclu QUOI, avec ses preuves.

## Comparaison avec l'architecture ARENA existante (audit préalable, §3)

| Capacité | État ARENA avant cette mission | Verdict |
|---|---|---|
| Agent finance | `agents/finance/finance_agent.py` — ACTIF, mais **marché financier (crypto)**, pas finance d'affaires (marge, trésorerie de projet) | Ne couvre pas le besoin — réutilisé pour son PATTERN (calcul déterministe → interprétation), pas pour son code |
| Chiffrage métier | `agents/plaquiste/` — ACTIF, calcul de matériaux/main-d'œuvre pour UniC Plaquiste | Réutilisé comme SOURCE de contexte métier (`config/metier.yaml`), jamais dupliqué |
| Recherche web | `tools/search/web_search_tool.py` — ACTIF, déjà partagé par Finance/Researcher/Trend | Réutilisé tel quel pour le rôle `strategie_marche` |
| RAG documentaire | LightRAG (`RAG_DOCS`) + GraphRAG (`GRAPHRAG`) — ACTIFS | Réutilisés via le callback `lightrag_query`, aucun second RAG |
| Graphe de connaissances | `core/connectors/graphify.py` — ACTIF (VOLET Graphify) | Non câblé dans cette mission (aucun besoin de relation structurée company→project→supplier n'a été mesuré comme bloquant pour le MVP) — **limite documentée**, pas oubliée |
| Mémoire | `core/memory/memory_manager.py` — ACTIF, SQLite (court terme + faits long terme) | Étendu (`list_facts`, une méthode, pas un second système) pour la mémoire de décision |
| Aiguillage/routeur de tâche | `agents/orchestrator/orchestrator_agent.py` (intentions), `apps/backend/routers/chat.py` (dispatch) — ACTIFS | Étendu avec une intention `EXECUTIVE` de plus, jamais un second aiguilleur |
| Sélection dynamique de méthode | `core/specialistes/catalogue.py`/`selection.py` — ACTIF, mais scope code/plaquiste, mécanisme à UN seul appel modèle (injection de méthode dans un prompt partagé) | Pattern repris (mots-clés pondérés, déterministe, plafond) dans `core/executive/selection.py`, avec sa PROPRE table de rôles d'affaires — les deux mécanismes coexistent, ils ne se recouvrent pas |
| Voies d'exécution / coût modèle | `core/execution/voies.py` — ACTIF | Étendu (`EXECUTIVE → RECHERCHE`), jamais un second système de budget |
| Registre d'agents cross-espace | `core/agent/capacites.py` — ACTIF | **Non étendu** : ce registre ne connaît que les espaces choisissables dans la barre latérale de la PWA (`INTENTION_PAR_ESPACE`) — "Executive" n'en est pas un. Une première tentative d'y enregistrer `"executive"` a été **détectée en régression** par `tests/test_runtime_capacites.py` (suite complète) et retirée — voir Vérification |
| Permissions | `config/permissions_services.yaml` — ACTIF | **Non modifié** : l'Executive Intelligence ne passe par aucun connecteur d'écriture — elle recommande, elle n'exécute rien (§23/§24) |
| Stratégie, marketing, RH, juridique | **ABSENTS** avant cette mission | Nouveaux rôles légers (`core/executive/specialistes.py`), chacun adossé à une capacité réelle (recherche web, document, ou modèle seul avec `UNKNOWN` explicite si aucune donnée n'existe) |

**Aucun agent-plateforme dupliqué. Aucun second registre, routeur, RAG ou système de
mémoire.** Le tableau ci-dessus est la preuve écrite de la règle §4/§47.

## Ce qui a été adopté d'OpenExecutive

1. Le principe même d'une couche « Executive » qui coordonne des spécialistes plutôt que
   de tout traiter elle-même.
2. Le parallélisme des consultations (`asyncio.gather`), avec un plafond de fan-out —
   repris comme concept, implémenté indépendamment (`core/executive/moteur.py`).
3. Le repli du Comité sur deux rôles « les plus transverses » quand aucun domaine précis
   n'est nommé — adapté en `ROLES_PAR_DEFAUT = ("finance", "risque")` dans
   `core/executive/selection.py`, pour couvrir une demande d'évaluation générale (mission
   §40) sans jamais convoquer tous les rôles par défaut.
4. La porte d'autorité à plusieurs issues (`departments/authority.py`) — **concept
   reconnu comme équivalent** au système de permission d'ARENA
   (`config/permissions_services.yaml`, CONFIRMATION/ALLOWED/DENIED). Non réimplémenté :
   ARENA a déjà ce mécanisme, plus mature (audit, journal, interrupteurs).

## Ce qui a été explicitement rejeté

1. **La voix unique qui masque l'architecture interne.** Rejeté : la mission demande une
   traçabilité par rôle (§29/§38).
2. **ChromaDB.** Rejeté : ARENA a déjà un RAG (LightRAG/GraphRAG). Aucune raison d'ajouter
   une seconde base vectorielle (mission §17).
3. **Le calcul financier confié au modèle.** Rejeté : `core/executive/calcul_affaires.py`
   calcule, le modèle interprète seulement (mission §13).
4. **Les intégrations Slack/Discord/Telegram/Google Chat.** Non reproduites : ARENA a déjà
   ses propres connecteurs de communication (email, réseaux sociaux) ; les ajouter ici
   aurait dupliqué une infrastructure existante sans besoin mesuré (mission §35).
5. **Le `decision_ledger` à cycle d'autonomie progressive** (Build 3). Trop en avance sur le
   besoin mesuré ici : ARENA n'a pas encore d'action exécutive AUTO_EXECUTE à graduer.
   Documenté comme piste future, pas construit.
