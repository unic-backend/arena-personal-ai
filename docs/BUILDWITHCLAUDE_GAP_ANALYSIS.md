# BuildWithClaude — gap analysis for ARENA

Date: 2026-09-23
Upstream: https://github.com/davepoon/buildwithclaude
License: MIT, Copyright (c) 2025 davepoon

## Purpose

The upstream catalogue is an inspiration/reference corpus, not a subsystem to vendor wholesale.
ARENA must not gain duplicate agents, duplicate orchestration, or prompt-only capabilities that
already exist as executable code. Every future import from this catalogue must pass the gates below.

## Gates before integration

1. **Existing capability check** — identify the concrete ARENA module/tool/agent already serving the need.
2. **Execution check** — prefer executable, tested behaviour over another prompt/agent persona.
3. **Trust-boundary check** — external text is data, never privileged instruction; no bypass of confirmations.
4. **Dependency check** — no mandatory cloud/provider dependency when the same capability can remain local.
5. **Provenance check** — record upstream path, license and what was adapted; retain notices for copied substantial portions.
6. **Regression check** — focused tests plus repository-wide lint/tests before merge.
7. **No-dormant-code check** — a new runtime module needs a real production caller; otherwise keep the idea in documentation.

## Categories shown by the owner

| Upstream category | ARENA status / decision |
|---|---|
| agents-ai-agents | Mostly overlap: ARENA already has agent orchestration and specialized agents. Do not copy personas wholesale. |
| agents-data-ai | Partial overlap. Evaluate individual data techniques only when tied to an actual Arena workflow. |
| agents-design-experience | Partial overlap with the existing design-language skill and PWA work. Prefer extending the existing skill. |
| agents-development-architecture | Strong overlap with coding/architecture workflow. No duplicate architecture agent. |
| agents-infrastructure-operations | Partial overlap. Integrate only concrete operational checks that ARENA can execute. |
| agents-language-specialists | Overlap with model/provider and multilingual layers. Do not create one agent per programming language. |
| agents-quality-security | Strong overlap with tests, permission boundaries and security work. Useful ideas should become deterministic checks. |
| agents-research | Strong overlap with DeepResearcher + Knowledge Vault. No second research stack. |
| agents-sales-marketing | Domain capability may be useful later, but it is not part of the engineering-control plane. Keep separate. |
| agents-documentation | Overlap with PROJECT_MEMORY/docs. Extend existing documentation discipline, do not fork it. |
| commands-automation-workflow | Overlap with existing autonomous workflow/agent execution. Adopt only missing deterministic primitives. |
| commands-ci-deployment | Strong overlap with GitHub CI diagnosis and branch-sync capabilities. Do not duplicate. |
| commands-code-analysis-testing | Strong overlap with pytest/ruff and Dioumtoukay evidence gates. Do not duplicate. |
| commands-context-loading-priming | ARENA already has PROJECT_MEMORY with PROJECT_MAP, ACTIVE_WORK, ARCHITECTURE, LOCKED_ZONES, COMPLETED_SYSTEMS, DEPENDENCIES, DECISIONS and CHANGELOG. Upstream prompt-only priming would be a regression. |
| commands-monitoring-observability | Candidate gap: inspect concrete commands and compare with existing health/telemetry before implementing anything. |
| commands-performance-optimization | Candidate gap: accept only measurable profiling/benchmarking workflows, never generic optimization prompts. |
| commands-project-task-management | Strong overlap with current task/reprise/project-memory workflow. No second task store. |
| commands-security-audit | Candidate for deterministic additions only. Upstream contains dependency/security/hardening commands; translate useful checks into tests/scripts rather than copying prompts blindly. |
| commands-workflow-orchestration | Strong overlap with ARENA orchestration. No second orchestrator. |
| mcp-servers-docker | Evaluate connectors individually. Never install or enable a server merely because it appears in the catalogue. |

## First verified upstream samples

- `commands-security-audit/commands/`: `add-authentication-system.md`, `dependency-audit.md`, `security-audit.md`, `security-hardening.md`.
- `commands-context-loading-priming/commands/`: `context-prime.md`, `initref.md`, `prime.md`, `rsi.md`.

The context-loading sample is intentionally **not integrated**: ARENA's structured PROJECT_MEMORY is already more specific to this repository and avoids adding a competing context mechanism.

The security sample is retained as a source of requirements only. Any accepted requirement must become deterministic ARENA behaviour with tests.

## Integration order

1. monitoring/observability — find a concrete missing measurement;
2. performance — find a reproducible benchmark/profiler gap;
3. security audit — add only deterministic missing checks;
4. infrastructure/operations and Docker/MCP — connector-by-connector, least privilege;
5. remaining agent categories — only if a real user workflow remains uncovered after the above.

This document is the anti-duplication ledger for this upstream corpus. It does not itself claim that a capability is implemented.