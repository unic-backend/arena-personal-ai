# Connector validation

This matrix separates simulated coverage from evidence obtained against a real external service.

Status vocabulary: **PASS**, **FAIL**, **SKIPPED**, **NOT_TESTED** only.

| Connector | Unit | Mock | Real Auth | Real Read | Permission | Privacy | E2E |
|---|---|---|---|---|---|---|---|
| Gmail | PASS | PASS | SKIPPED | SKIPPED | PASS | PASS | SKIPPED |
| Google Calendar | PASS | PASS | SKIPPED | SKIPPED | PASS | PASS | SKIPPED |
| GitHub | PASS | PASS | SKIPPED | SKIPPED | PASS | PASS | SKIPPED |
| Agent Reach | PASS | PASS | SKIPPED | SKIPPED | PASS | NOT_TESTED | SKIPPED |

## Interpretation

PASS in Unit/Mock means the repository's offline suite exercises the connector contract; it is **not** proof that the provider accepted a credential. Real Auth/Real Read/E2E remain SKIPPED until the opt-in real-integration suite runs with the provider credentials and services required by that test.

Sensitive write capabilities (send, publish, delete, remote mutation) are never exercised against a production account by the real-health suite. They remain protected by `ControleAcces` and the confirmation queue. Real validation uses safe read-only operations unless an explicit sandbox exists.

## Opt-in contract

Real tests are disabled in the normal offline suite. They require:

```
RUN_REAL_INTEGRATION=1 pytest tests/integration/ -q
```

A missing credential/service must produce **SKIPPED — REAL_INTEGRATION credentials unavailable**, never PASS. Credentials are read only from the environment/CI secret store and must never be committed or printed.

## Evidence required before changing SKIPPED to PASS

A real connector row can become PASS only after a run proves configuration, authentication, provider connection, granted permission/scope, a harmless read, expected response shape, bounded timeout, sanitized errors/logs, and no bypass of ARENA's permission layer.