# VOLET — ARENA as a personal AI operating system

Opened 2026-08-27 on the owner's 30-section specification. The audit that
justifies this order is `docs/AUDIT_ARENA_OS.md`; it was measured, not recalled.

```
VOLET en cours   : ARENA OS
Chapitres        : 12
Phases           : 21
Phase courante   : 3.2 — en attente de confirmation
Terminées        : 1.1 (2026-08-27) — `core/actions/resultat.py`, sept statuts ;
                   un succès exige une preuve, une action sans effet n'en porte pas.
                   2.1 (2026-08-27) — `core/actions/journal.py`, les neuf champs ;
                   aller-retour SQLite intact, secrets masqués avant écriture.
                   2.2 (2026-08-27) — journal branché sur le chemin réel,
                   `core/actions/timeline.py` et `GET /api/actions`.
                   3.1 (2026-08-27) — `core/permissions/politique.py` et
                   `config/permissions_services.yaml` : compte × service ×
                   action × risque, action inconnue refusée.

**Correction apportée au plan par la spécification.** Ce tableau annonçait
`delete = DENIED` pour l'e-mail. Le §13 de la spécification du propriétaire dit
`delete = confirmation required`, et c'est elle qui fait autorité : la valeur
livrée est `CONFIRMATION`. Une ligne du YAML suffit à la durcir en `DENIED` s'il
le souhaite.
```

---

## The plan

```
Ch. 01  Vérité des états            → 1 phase (indivisible)
Ch. 02  Journal d'actions           → 2 phases
Ch. 03  Permissions granulaires     → 2 phases
Ch. 04  Cadre de connecteurs        → 2 phases
Ch. 05  Confirmation humaine        → 2 phases
Ch. 06  Mémoire personnelle         → 4 phases
Ch. 07  Exécution adaptative + mesures → 2 phases
Ch. 08  Connecteur e-mail           → 2 phases
Ch. 09  Connecteur agenda           → 1 phase (indivisible)
Ch. 10  Travaux de fond             → 1 phase (indivisible)
Ch. 11  Appels d'offres Sénégal     → 1 phase (indivisible)
Ch. 12  Site web, SEO, Google Business, réseaux → 1 phase (indivisible)
```

**Total : 21 phases.**

## Detail

| Phase | What it does | How it is verified |
|---|---|---|
| **1.1** | `TikTokConnector` and `PublisherAgent` stop reporting `success` for a simulation. A third state, `NOT_CONFIGURED`, is introduced and returned. §27. | a test asserts no code path returns `status: success` without a verified external effect |
| **2.1** | `ActionRecord` — id, timestamp, tool, target, parameters, permission level, result, errors, verification status. §12. | round-trip through SQLite, every field preserved |
| **2.2** | `agent_logs` finally written, and an activity timeline readable. §21. | an action executed end to end appears in the timeline with its verification state |
| **3.1** | `Permission(account, service, action, risk)` next to the nine booleans, which keep working. §13. | `send` and `delete` on Gmail = CONFIRMATION, `settings` = DENIED, by default and from config |
| **3.2** | Every existing call site moves onto the scoped check; the dead `PERM_*` variables are removed or wired. | the two current `is_allowed` sites still refuse what they refused |
| **4.1** | `Connector` base: auth, capabilities, permissions, health, read ops, write ops, errors, rate limits, audit. §16. | a connector declaring nothing exposes nothing |
| **4.2** | Lazy connector registry, replacing hard-coded branches. A broken connector degrades alone. | the server starts with a connector that raises on construction |
| **5.1** | `PendingAction` — action, target, risk, expected result — held, shown, then executed or dropped. §18. | an unconfirmed action never executes |
| **5.2** | `/api/actions` — list, confirm, cancel; and the owner's automation policies. | confirming twice executes once |
| **6.1** | Memory schema: episodic, semantic, procedural, task; entities and relations; importance, recency, source. §2. | migration keeps the existing rows |
| **6.2** | Retrieval: keyword + metadata + temporal, scored, with a hard budget. | "the project from four months ago" finds it; retrieval stays under budget |
| **6.3** | Semantic retrieval, local embeddings only. | measured on the owner's machine, or reported `BLOCKED` |
| **6.4** | Consolidation and summaries; FACT / PREFERENCE / INFERENCE / TEMPORARY kept distinct. §19. | an inference never becomes a fact |
| **7.1** | Formalise the four existing lanes (instant, light, deep, research) and their budgets. §14. | a simple question never reaches deep reasoning |
| **7.2** | Benchmarks: first token, simple, normal, complex, retrieval, search, tool. §25. | figures measured on his machine, or `UNKNOWN` |
| **8.1** | Gmail connector, official API, **read and search only**. §3. | tested against a mock; `NOT_CONFIGURED` without credentials |
| **8.2** | Classification, extraction, drafting; sending behind confirmation. §4. | sending without confirmation is impossible, and the test proves it |
| **9.1** | Calendar: read, free slots, conflicts; writes behind confirmation. §5. | same |
| **10.1** | Background jobs that never block the chat. §15. | chat latency unchanged while a job runs |
| **11.1** | Senegalese tenders: search, extraction, ranking, source + retrieval date. §10. | no opportunity without its source; nothing invented |
| **12.1** | Website, SEO, Google Business, social: real clients, `NOT_CONFIGURED` until the owner connects them. §6–9. | no simulated publication anywhere |

---

## What this VOLET does not do

- **It does not rewrite the orchestrator.** Its two deterministic pre-gates are
  the adaptive execution §14 asks for; they are extended, not replaced.
- **It does not rebuild `fresh_info`.** §11 is largely already met.
- **It does not connect any account by itself.** Chapters 8, 9 and 12 end at a
  real client plus `NOT_CONFIGURED`. Only the owner can supply OAuth
  credentials, and only on his machine.
- **It does not measure latency here.** No GPU, no `ollama serve` in this
  environment. §25 figures come from his machine or stay `UNKNOWN`.

## The one thing that gates chapter 8

Six secrets are still in this public repository's git history and the keys have
not been rotated. An OAuth token added before that is done inherits the same
exposure. Chapter 8 should not be switched on for a real account until the
rotation and the history purge are finished — both are prepared, neither has
been authorised.
