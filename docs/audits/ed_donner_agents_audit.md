# Audit — `ed-donner/agents` : intégration sélective (30/09/2026)

**Dépôt audité** : `https://github.com/ed-donner/agents`, commit amont
`da8933700ed2255518c2725cad976008c2be23e0` (19/09/2026), licence **MIT**.

**Ce que c'est** : le dépôt d'un cours (« AI Agentic Engineering », six
semaines). Mesuré : **3 189 fichiers Python et 757 notebooks au total** ; le
cours lui-même, hors `community_contributions/` (devoirs d'étudiants), en
pèse **122 et 37**. Les notebooks sont le support de cours ; les applications
(twin, trading floor, sidekick) sont des démonstrateurs didactiques. **Aucune
partie n'a été copiée dans ARENA.**

**Méthode** : lecture des sections demandées (`1_foundations/`, `2_openai/`,
`3_crewai/`, `4_langchain_langgraph/`, `5_agent_frameworks/`, `6_mcp/`,
`guides/`), séparation stricte « exemple pédagogique → patron d'ingénierie →
valeur de production pour ARENA », puis comparaison capacité par capacité
contre le code d'ARENA **tel que mesuré** (modules ouverts et lus, contrats
exécutés dans le test de retenue — rien de déduit).

---

## 1. Ce que contient chaque section

| Section | Contenu mesuré | Nature |
|---|---|---|
| `1_foundations/` | boucle d'appels d'outils sur `chat.completions` (tant que `finish_reason == "tool_calls"`), « digital twin » avec **évaluateur** (un second appel juge la réponse et la fait recommencer) | pédagogique |
| `2_openai/` | OpenAI Agents SDK : handoffs, agents-comme-outils, **sorties structurées** (`output_type` Pydantic), **guardrails** (agent vérifieur, `output_guardrail`), session mémoire SQLite, pipeline *deep research* (planificateur → recherches **parallèles** → rédacteur → e-mail), traces `platform.openai.com` | cadre + démonstrateurs |
| `3_crewai/` | CrewAI : rôles/agents/tâches, processus séquentiel et hiérarchique, `coder` crew exécutant son code dans Docker | cadre + démonstrateurs |
| `4_langchain_langgraph/` | graphes d'état avec réducteurs, `create_agent`, middlewares (TodoList, PII, limite d'appels modèle, **HumanInTheLoop**), *Sidekick* : ouvrier + **boucle évaluateur bornée** (critères de succès explicites, max 3 tentatives avec retour), erreurs d'outils **rendues comme message** au modèle | cadre + démonstrateur |
| `5_agent_frameworks/` | Google ADK (+ A2A), Strands, Pydantic AI, Microsoft Agent Framework, agno, Mastra ; table de travail **SQLite partagée en WAL** entre agents ; agent **QA qui vérifie indépendamment** le travail (joue vraiment le jeu construit dans un navigateur) ; **contrôle final déterministe hors de l'agent** (`is_built`) ; démonstrateur : une arcade HTML de jeux d'apprentissage des langues assemblée à chaud par les ouvriers | cadres + patron |
| `6_mcp/` | serveurs FastMCP (outils + **ressources** `@mcp.resource`), clients stdio (« le processus EST la session »), **filtre statique d'outils** (`create_static_tool_filter` — ne donner à un agent que les outils choisis), « context engineering » (mémoire graphe + recherche web + RAG agentique), traceur `TracingProcessor` écrivant chaque span en base | pédagogique + patrons |
| `guides/` | guides débutant : terminal, git, Python, async, Ollama. Le propriétaire d'ARENA **n'écrit pas de code** (`docs/REGLES_DE_TRAVAIL.md`) | hors périmètre |

## 2. Table de comparaison des capacités

Convention : **A** déjà implémenté · **B** patron utile déjà atteignable par les
abstractions existantes · **C** capacité réellement manquante · **D** intéressant
mais inutile aujourd'hui · **E** refusé.

| Capacité | ARENA l'a déjà ? | Implémentation externe | Amélioration réelle | Décision |
|---|---|---|---|---|
| Orchestration d'agents | **Oui** — `agents/orchestrator` (classement d'intention, modèle puis repli mots-clés) → `dispatch_request` ; `core/agent/equipe.py` fait travailler plusieurs agents sur une demande (découpage déterministe, résultat passé enveloppé) | handoffs (OpenAI SDK), crews (CrewAI), boucle d'orchestrateur (ADK) | aucune mesurable | **A** |
| Transfert d'agent en agent | **Oui** — syntaxe fermée `[[COLLEGUE:…]]` / `[[COMPETENCE:…]]` (registre, `CONSULTATIONS_MAX = 2`) | `handoff=` du SDK | équivalent sans dépendance | **A** |
| Découpage de tâches | **Oui** — `equipe.py` (connecteurs explicites), `core/execution/coordination.py` (`Etape`, dépendances, étapes facultatives) | planificateur *deep research*, tâches CrewAI | aucune mesurable | **A** |
| Appel d'outils + permissions | **Oui, plus fort** — `core/connectors/base.py` : capacité déclarée → permission → **confirmation** → santé → quota → crochets → journal. Le cours n'a ni permission, ni confirmation, ni journal | `@function_tool`, outils CrewAI | aucune (ARENA l'exige) | **A** |
| Confirmation humaine | **Oui** — `core/actions/attente.py` (confirmer deux fois n'exécute qu'une fois), `core/executive/question_en_attente.py` (l'agent pose une question, la réponse fait reprendre) | `HumanInTheLoopMiddleware` (interruption + reprise) | aucune | **A** |
| Mémoire | **Oui, plus fort** — `core/memory/` (personnelle ×4 natures, récupération lexicale+sémantique, consolidation, contradiction, chiffrement), `core/knowledge/` (vault, BM25+RRF) | serveur mémoire « knowledge graph » (composant externe), `SQLiteSession` du SDK | aucune | **A** |
| Gestion de contexte | **Oui** — budgets de voie (`core/execution/voies.py`), enveloppage `trust.py`, fil de conversation relu par `conversation_id`, budget mémoire du prompt | « context engineering » (mémoire+recherche+RAG dans le prompt) | aucune | **A** |
| Boucle agentique bornée | **Oui** — `core/execution/boucle.py` : budgets écrits (étapes/tours/temps/outils), `RaisonDArret` sur 8 sorties, échecs cumulés, anti-répétition, replanification | boucle ouvrier/évaluateur bornée (3 tentatives), `ModelCallLimitMiddleware` | aucune | **A** |
| Sorties structurées | **Oui, autre forme** — convention `core/finance/structured_output.py` : dataclass figé, `to_dict()`, clés fixes, provenance obligatoire (audit AutoHedge) | `output_type` Pydantic dans le SDK | passer ces dataclasses par un schéma Pydantic n'ajoute aucune garantie exécutée ici | **B** |
| Garde-fous | **Oui, plus fort** — frontière de confiance (`trust.py`), politique compte×service×action×risque, disjoncteur, `verification_synthese.py` (agents cités absents, chiffres sans source), `controle_prix.py` | `output_guardrail` (agent vérifieur) | le garde-fou d'ARENA est déterministe **avant** le modèle ; celui du cours est un jugement de modèle **après** | **A** |
| Évaluation | **Oui, par conception déterministe** — vérification d'étape de `coordination.py`, critique indépendante → révision bornée (`reasoning_engine.py`), contrôle final hors de l'agent (`verification_synthese`) ; `core/observabilite/plans.py` dit sciemment « aucun plan n'est jugé ici » | évaluateur-LLM (twin, sidekick), agent QA qui rejoue le travail | un évaluateur-LLM générique contredirait deux principes écrits (« la mesure d'abord, jamais un jugement ») — décision de conception, pas un trou | **A/B** |
| Erreur d'outil | **Oui** — `core/actions/resultat.py` (une panne est un statut, jamais un faux succès) ; transports MCP : « une panne est un état, jamais une exception » | `TolerateToolErrors` (l'échec devient message au modèle) | aucune | **A** |
| Exécution longue / reprise | **Oui** — `travaux.py` (file bornée), `journal_disque.py`, `reprise.py` (amorce/confirmation, état inconnu rapporté tel quel), checkpoint/restauration (`tools/atelier/git_ops.py`) | boucle `while True` du trading floor | aucune | **A** |
| État partagé multi-agents | **Oui** — SQLite WAL partagé (mémoire, journal, `journal_projet.py` branché sur l'observateur de `Coordination`) | `board.py` (SQLite WAL + busy_timeout) | aucune, même forme choisie ici avant (DEC-0090) | **A** |
| Client MCP — outils | **Oui** — deux transports : HTTP streamable (`core/mcp/transport.py`, WanGP) et stdio (`core/mcp/stdio_transport.py`, OpenTakeoff, Codebase-Memory) ; notifications filtrées ; pas de dépendance nouvelle | `MCPServerStdio` du SDK, lab fetch/playwright/filesystem | aucune | **A** |
| Serveur MCP | **Oui** — `core/mcp/memory_server.py` (6 outils, SDK `mcp==2.1.1`, gouvernance : un client externe n'écrit jamais un FAIT) | FastMCP `@mcp.tool` | aucune | **A** |
| MCP — **ressources** et **prompts** | **Non, mesuré** — les deux transports n'implémentent que `initialize`/`tools/list`/`tools/call` ; le serveur mémoire n'expose que des outils | `@mcp.resource("accounts://…")` lu en `session.read_resource` | **aucun consommateur réel n'est démontré** — voir §3 | **D** |
| MCP — filtre statique d'outils | **Déjà atteint structurellement** — chaque connecteur n'importe qu'un sous-ensemble réel d'outils (OpenTakeoff : « rien qui devine une coordonnée », DEC-0012) et la politique de permissions borne chaque action | `create_static_tool_filter(allowed_tool_names=[…])` | aucune ligne à ajouter | **B** |
| Observabilité | **Oui** — `mesures.py` (durée par voie, `/api/observability`), `journal.py` (9 champs, secrets masqués), chronologie, journal des plans, fil d'observabilité | `LogTracer` : chaque span en base, tableau en direct | export de traces externe : voir §4 (D) | **A** |
| Abstraction de fournisseurs / local-first | **Oui** — `core/models/routeur.py`, Ollama défaut et repli, confidentialité 4 niveaux, `AI_LOCAL_ONLY` | « use any OpenAI-compatible endpoint » | ARENA l'exige, le cours ne le garantit pas | **A** |
| Protocole A2A (agents en réseau) | Non | `1_google_adk_a2a` | réseau de clés, de quotas et de tiers — contraire au local-first et à la frontière de confiance | **E** |
| Outils hébergés OpenAI (`WebSearchTool`, traces `platform.openai.com`) | Non, et ne sera jamais | 2_openai, 6_mcp | envoie le trafic et les journaux chez un fournisseur | **E** |
| Cinq frameworks d'orchestration comme dépendances | Non, et refusés (§5) | CrewAI 1.14.4, LangGraph, OpenAI Agents SDK, Google ADK, Pydantic AI, MAF, agno, Strands, Mastra | cinq orchestrateurs pour une architecture déjà présente ; `requirements.txt` ne le paiera jamais — tenu par un test | **E** |
| Notebooks / laboratoires / démonstrateurs | Non, et refusés (§12) | 37 notebooks, trading floor, sidekick | pédagogie, pas de production | **E** |
| Contenu inconnu | — | — | rien d'autre de mesuré dans les sections demandées ; `community_contributions/` (922 dossiers de devoirs d'étudiants) n'est pas auditée individuellement, par conception | UNKNOWN |

## 3. MCP : examen approfondi (mission §6)

**Ce qu'ARENA parle déjà** : `initialize` + `notifications/initialized`,
`tools/list`, `tools/call`, sur deux transports (HTTP streamable et stdio), avec
deux propriétés que le cours n'a pas : les notifications intercalaires sont
ignorées jusqu'à la bonne réponse (mesuré sur le vrai serveur OpenTakeoff), et
la lecture stdio fonctionne sous Windows (`select()` n'y accepte pas un pipe —
remplacé par un thread + `queue.Queue`, défaut réellement corrigé le
29/08/2026).

**Ce qu'il ne parle pas** : `resources/list`, `resources/read`, `prompts/list`,
`prompts/get`. C'est une abstention **délibérée et documentée** dans le
transport (« Ce qui n'est pas là n'existe pas »), pas un oubli.

**Faut-il les ajouter ?** Le critère est : un consommateur réel, aujourd'hui.

- **OpenTakeoff** annonce bel et bien `notifications/resources/list_changed`
  après `load_plan` — donc il *possède* des ressources. Mais le métré d'ARENA
  obtient déjà toutes ses données par `tools/call` (`detect_rooms`,
  `compute_areas`…), chemin vérifié bout en bout contre le vrai serveur.
  Lire les ressources du plan n'ajouterait qu'un second accès aux mêmes
  données.
- **Le serveur mémoire d'ARENA** n'a pas non plus besoin de ressources : ses
  six outils suffisent à tout ce qu'un client MCP vient y faire ; ajouter
  `memory://souvenirs/…` créerait une seconde surface sans consommateur —
  **exactement** ce que DEC-0204 vient de refuser chez Basic Memory.
- **WanGP** : non mesuré dans cet environnement (service absent du conteneur
  — `NOT_CONFIGURED` honnête). Sa surface utile est consommée par
  `wan2gp.generer`, un outil.

Conclusion : capacité protocolaire réellement absente du client, **sans besoin
démontré**. Catégorie **D** — suggestion, non implémentée. Si un service
intégré un jour expose une ressource indispensable, le plus petit ajout est
écrit ici pour ne pas le redécouvrir : ajouter `ressources()` et
`lire_ressource(uri)` aux deux transports, derrière le même `Reponse`, et un
test contre un serveur de boucle local écrit pour l'occasion.

**Le filtre statique d'outils**, lui, est une leçon valide — et ARENA la tient
déjà par construction : un connecteur n'importe que le sous-ensemble déclaré
d'un serveur lointain, et la politique `compte × service × action × risque`
borne chacune d'elles. Rien à ajouter (**B**).

## 4. Suggestions — NON IMPLÉMENTÉES

1. **`resources/read` et `prompts/get` sur les deux transports MCP** — le jour
   où un serveur intégré les expose. Aujourd'hui : aucun consommateur.
2. **« Demande d'aide humaine » pour l'agent navigateur** (patron
   `request_human_help` du Sidekick : l'agent rapporte exactement quoi faire —
   ouvrir une session, résoudre un captcha — puis **reprend la même session**).
   L'équivalent conversationnel existe (`question_en_attente`), mais pas pour
   une session de navigateur persistante. Conception vérifiée sur sa machine
   seulement : unknown depuis le conteneur, et la navigation visible chez lui
   est un prérequis. À étudier seulement si le besoin revient.
3. **Export de traces vers un observateur externe** (patron `LogTracer`) —
   `core/execution/hooks.py` (`apres_execution`) est le point naturel ; inutile
   sans observateur réellement regardé.

## 5. Refusés — catégorie E, avec la raison mesurée

| Refus | Raison |
|---|---|
| CrewAI, LangGraph, OpenAI Agents SDK, Google ADK, Pydantic AI, agno, Strands, MAF, Mastra, deepagents comme dépendances | Mission §5 : cinq orchestrateurs concurrents pour aucune capacité manquante (§2) ; le contradicteur direct des zones verrouillées (un orchestrateur nourri en plus de `boucle.py`/`coordination.py`/`equipe.py` casserait les garanties mesurées, **sabotage-testées**). Tenue par `tests/test_ed_donner_reste_dehors.py` |
| Traces `platform.openai.com`, outils hébergés OpenAI | journaux et trafic vers un fournisseur — contre DEC-0002/DEC-0009 (local-first / confidentialité) |
| A2A (agent ↔ agent en réseau) | exposition réseau d'actions autonomes — contraire à la frontière de confiance et au caractère personnel/local d'ARENA |
| Copie de notebooks, d'labs, du trading floor, du sidekick | supports de cours ; « jamais de notebooks en production » (mission §12) |
| `guides/` | guides débutant terminal/git/Python — le propriétaire n'écrit pas de code (`docs/REGLES_DE_TRAVAIL.md`) |

## 6. Dépendances et licences

- Amont : **MIT** — aucune restriction à étudier les patrons. **Aucune ligne de
  code copiée** (ni Python, ni configuration, ni prompt) : le `NOTICE.md` et
  `THIRD_PARTY_NOTICES.md` d'ARENA restent inchangés, vérifié.
- **Aucune dépendance ajoutée.** Deux exceptions préexistantes à ne pas
  confondre avec une adoption : `langchain-openai==1.1.14` (substrat exigé par
  `browser-use`, épinglé pour PYSEC-2026-76, pas un orchestrateur) et
  `mcp==2.1.1` (le SDK protocolaire, utilisé par le serveur mémoire d'ARENA,
  DEC-0090) étaient déjà présents avant cet audit.
- `requires-python = ">=3.12"` côté amont : un des motifs indépendants déjà
  mesurés dans DEC-0204 chez un autre projet ; ARENA tourne en 3.11.

## 7. Ce qui est livré

1. **Ce document** — l'audit complet et la classification.
2. **`tests/test_ed_donner_reste_dehors.py`** — tient les deux moitiés de la
   décision : rien n'est entré (aucun framework dans les dépendances directes,
   aucun import dans le code suivi) **et** la raison pour laquelle rien n'a eu
   à entrer existe encore (les équivalents natifs sont exécutés, pas cités).
3. **`docs/DECISIONS.md`, DEC-0205** — la décision et ses coûts.
4. `PROJECT_MEMORY/DECISIONS.md` — index mis à jour.

**Aucun module de production n'est modifié.** Aucun comportement d'ARENA ne
change.
