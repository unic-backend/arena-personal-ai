# ARENA — audit of the existing system, before building the personal AI OS

Measured on 2026-08-27 on commit `2018f95`. Every number below was counted, not
recalled. Nothing here is a plan; the plan is `docs/PLAN_ARENA_OS.md`.

The owner's instruction was explicit: *"Do not assume functionality exists
simply because a file exists. Trace the real execution paths."* So this document
is organised by what actually runs, not by what is on disk.

---

## 1. Size, measured

| Measure | Value |
|---|---|
| Python files (excluding `.venv`) | 130 |
| Python lines | 13 147 |
| Agents | 17 |
| HTTP routes | 8 |
| Tests | 681 passing, 21 deselected |
| Connectors | 1, and it is a simulation |

ARENA is small. That is good news: the foundations asked for in §13, §16 and §21
can be built without fighting an existing framework.

---

## 2. The real execution path

One path carries every request:

```
POST /api/chat            (apps/backend/routers/chat.py)
  → verify_api_key + limiter_debit          security.py
  → orchestrator.analyze_intent(prompt)     agents/orchestrator/
       1. question_personnelle()  → CHAT     deterministic, no model
       2. exige_verification()    → FRESH_INFO  deterministic, clock-based
       3. model classifier, closed set of 14 labels
       4. keyword fallback if the model is unusable
  → dispatch_request()  →  one of 14 branches
  → memory.add_chat_message()  ×2
```

**This is already the adaptive execution the owner asks for in §14**, and it is
better than it looks: two deterministic gates run *before* the model, so the
cheap answer never pays for the expensive one. It is the seam every new
capability should hang from. It does not need replacing.

What it lacks: no branch can *act* on the outside world, none records what it
did, and none can be refused by a scoped permission.

---

## 3. What is real

| Component | State | Note |
|---|---|---|
| `OrchestratorAgent` (311 l.) | **REAL** | closed intent set, deterministic pre-gates, logged fallback |
| `security.py` (83 l.) | **REAL** | Bearer key, rate limit, path-traversal guard |
| `fresh_info` chain (308 l.) | **REAL** | search → fetch → context budget → synthesis → numbered sources |
| `MemoryManager` (116 l.) | **PARTIAL** | see §5 |
| `PermissionManager` (59 l.) | **PARTIAL** | see §4 |
| `ReasoningEngine` (63 l.) | **REAL** | plan → sandboxed Python → synthesis |
| `PlaquisteAgent` + 4 modules | **REAL** | prices and material ratios from the owner's own quotes |
| `TikTokConnector` (24 l.) | **SIMULATION** | see §6 |

**§11 (autonomous research) is largely already built.** `fresh_info` collects
sources, reads pages in parallel, budgets the context, cites `[1] [2]`, and
`_sources_de_secours()` degrades to engine snippets rather than inventing.
Provenance survives. This chapter is a *verification* job, not a build job.

---

## 4. Permissions — real, but the wrong shape

`core/permissions/permission_manager.py` holds **nine global booleans** in
`config/permissions.yaml`: `READ_FILES`, `WRITE_FILES`, `EXECUTE_COMMANDS`,
`SEARCH_WEB`, `DOWNLOAD_MEDIA`, `PROCESS_MEDIA`, `SEND_MESSAGES`, `PUBLISH`,
`DELETE`. Three are `false` by default, which is the right default.

Two problems, both measured:

- **Seven of the nine are never checked anywhere.** `grep is_allowed` over the
  source returns exactly two call sites: `PUBLISH` in `publisher_agent.py:33`
  and `WRITE_FILES` in `routers/media.py:89`. `SEND_MESSAGES: true` and
  `DELETE: false` currently govern nothing at all.
- **The shape cannot carry §13.** The owner asks for permissions scoped by
  ACCOUNT × SERVICE × ACTION × RISK. A single global `SEND_MESSAGES` boolean
  cannot say "read allowed on this Gmail account, send requires confirmation,
  delete forbidden". This is not something the booleans can grow into.

Also: `.env.example` declares `PERM_READ_FILES`, `PERM_WRITE_FILES`,
`PERM_EXECUTE_COMMANDS`, `PERM_AUTO_PUBLISH`. **Nothing reads them.** Dead
configuration that looks like a security control is worse than none: it invites
the owner to set `PERM_EXECUTE_COMMANDS=false` and believe something changed.

---

## 5. Memory — three tables, one of them empty by construction

`data/database/memory.db`, SQLite, created by `core/memory/memory_manager.py`:

| Table | Written by | Read by |
|---|---|---|
| `short_term_memory` | every chat turn | `get_recent_history(limit=6)` |
| `long_term_memory` | `set_fact()` — one call at startup (`owner`) | `get_fact(key)`, exact key only |
| `agent_logs` | **nothing** | **nothing** |

`grep agent_logs` over the whole source returns **one line**: the `CREATE TABLE`
itself. The audit table the owner asks for in §21 exists as a schema and has
never held a row.

Against §2, what is missing is nearly everything: no embeddings, no semantic
retrieval, no keyword index, no metadata filter, no temporal query, no
importance or recency score, no entities, no relations, no episodic/procedural
split, no summaries, no consolidation. `get_fact` matches an exact key or
returns `None`.

Concretely: **"continue the project we worked on four months ago" cannot work
today.** The chat prompt is built from the last six messages
(`chat.py:167`) and nothing else.

---

## 6. The finding that must be fixed before anything is built on it

`social/tiktok/tiktok_connector.py` returns, for a publication that never
happened:

```python
return {"status": "success", "simulated": True,
        "message": f"Vidéo '{title}' simulée comme publiée avec succès..."}
```

and `PublisherAgent` wraps that in `{"status": "success", ...}` too. The word
`simulated` is in the payload, but the *status field* — the field any caller
tests — says the publication succeeded.

This is precisely what §27 forbids ("Do not simulate publishing") and what
principle 7 forbids ("Never claim an action happened unless verified"). It is
also the pattern that would spread: an email connector written in the same shape
would report a sent mail that was never sent.

`SocialConnector` (20 l.) declares only `authenticate()` and `publish_video()`.
It has no capabilities, no permissions, no health, no rate limits, no audit
hook — it cannot carry §16 and should not be extended.

---

## 7. Architectural conflicts

1. **`apps/backend/runtime.py` builds all 17 agents at import time**, at module
   level. Every connector added the same way lengthens startup, holds resources
   whether used or not, and lets one broken constructor take the whole server
   down. Connectors must be lazy and individually failable.
2. **No connector registry.** `dispatch_request` is a 14-branch `if/elif` chain.
   §16 says explicitly: *"Do not hard-code everything into the orchestrator."*
3. **No action record.** Nothing in the codebase produces the
   `{action ID, timestamp, tool, target, parameters, permission level, result,
   errors, verification status}` tuple §12 requires.
4. **No confirmation object.** §18's flow ("Send it?" → "Send." → "Sent") has no
   representation: there is no pending action to hold, show, then execute.
5. **No background worker.** `grep BackgroundTasks|create_task|scheduler|cron`
   over the source returns nothing. §15 has no foundation.

---

## 8. Security, as it stands

Good, and worth keeping: Bearer key required or the gateway refuses to start
(`config.py`), CORS never `*`, path traversal blocked, rate limiting per client,
`EXECUTE_COMMANDS`/`PUBLISH`/`DELETE` false by default, secrets outside source.

Open, and it is the owner's to close: **six secrets remain in the git history**
of this public repository, and the keys have not been rotated. Any OAuth token
added before that is done inherits the same exposure. This is stated here
because §17 makes credential handling mandatory, and the first connector is the
moment it stops being theoretical.

---

## 9. Performance — no measurement exists

§25 asks for benchmarks. There is no latency measurement in the repository, and
none can be taken here: this container has **no GPU and no `ollama serve`**.
Every figure in §25 has to be measured on the owner's machine (RTX A2000 12 GB).
Until then, ARENA's latency is `UNKNOWN`, and this audit will not guess it.

---

## 10. What this means for the phase order

The owner proposed an order in §24 and asked that it be revised against what
exists. Three changes, each with its reason:

- **Research (his phase 5) moves down**, because `fresh_info` already does it.
  It becomes a verification and a wiring into memory, not a build.
- **Truth-of-status moves to the very front**, before phase 1. Building a
  connector framework on top of a component that reports success for a
  simulation would propagate the defect into every connector.
- **Audit trail and confirmation move ahead of the email connector**, because
  §18 and §21 are what make an email connector *safe to switch on*. Built
  afterwards, they would be retrofitted onto a connector already sending mail.

Nothing else in his order changes.
