# ECC selective integration audit

Upstream: `affaan-m/ECC` (Everything Claude Code), MIT license.

ARENA does **not** vendor or install ECC wholesale. ECC is primarily a developer
agent harness (agents, skills, hooks, commands and MCP configuration), while
ARENA is a Python/FastAPI personal-AI runtime with its own orchestrator,
permissions, memory, connectors, diagnostics and CI. Copying the full harness
would create parallel control planes and dormant components.

## Compared against ARENA

- Memory persistence: ARENA already owns `core/memory/` and `PROJECT_MEMORY/`.
- Agent orchestration: ARENA already owns `agents/orchestrator/` and
  `core/execution/`.
- Security review: ARENA already has `core/security/`, permission policies,
  gitleaks history/diff scans and least-privilege GitHub Actions.
- Performance: ARENA already has `scripts/performance_baseline.py`.
- Environment diagnostics: ARENA already has `scripts/doctor.py`.
- Dead integration detection: ARENA already has `scripts/orphelins.py`.
- MCP: ARENA already has native HTTP and stdio MCP transports.

Those areas are deliberately **not duplicated**.

## Capability adopted

ECC's `silent-failure-hunter` identifies swallowed exceptions and bare
fallbacks as a distinct engineering risk. ARENA did not have a deterministic
changed-code CI gate for that class.

ARENA therefore implements a small native AST gate in
`scripts/silent_failure_gate.py`. It is invoked by CI on Python files changed
by a PR (or the last commit on a push), reports exact file/line/rule, and fails
the build for bare `except` or an exception handler containing only `pass`.

This is an independent implementation of the review principle, not copied ECC
runtime code. ECC remains credited here as the design source.

## Why changed-code only

Turning on a repository-wide new rule without first establishing a clean
baseline would either break unrelated work or force broad cleanup into an
integration PR. Changed-code enforcement is reactive: every new/modified Python
path is protected immediately while existing behavior remains stable.

## Acceptance path

`developer change -> GitHub Actions -> silent_failure_gate -> pass/fail result`

The gate has unit tests for positive and negative cases. Ruff and the full
offline Pytest suite remain authoritative regression checks.
