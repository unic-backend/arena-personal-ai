# Security and connector audit

Audit baseline: `main@62e5fb85c626c3119d5f59568fa06ff80ffbcd35`.

## 1. Historical secrets — pre-rewrite report

The repository already records **7 Gitleaks findings representing 6 distinct historical plaintext values** in `.gitleaksignore`. They occur in historical versions of `librechat.yaml` and `docker-compose.yml`. No secret value is reproduced here.

| Identifier | Service/type | Historical locations | Still used? | Potentially valid? | Action |
|---|---|---|---|---|---|
| local_api_1 | ARENA local API credential | librechat.yaml | YES, equivalent API authentication still exists | UNKNOWN | ROTATE if not already proven rotated; purge history |
| local_api_2 | ARENA local API credential | docker-compose.yml | YES, equivalent API authentication still exists | UNKNOWN | ROTATE if not already proven rotated; purge history |
| creds_key_1 | retired LibreChat/Open WebUI internal secret | docker-compose.yml | NO | service retired | purge history |
| jwt_secret_1 | retired client JWT secret | docker-compose.yml | NO | service retired | purge history |
| jwt_refresh_1 | retired client JWT refresh secret | docker-compose.yml | NO | service retired | purge history |
| webui_secret_1 | retired Open WebUI application secret | docker-compose.yml | NO | service retired | purge history |

Known finding fingerprints currently suppressed by `.gitleaksignore`: 7. These are not treated as acceptable false positives; they are temporary evidence for the pre-rewrite repository and must disappear after a verified history rewrite.

Current configuration also contains narrowly-scoped synthetic-fixture allowlists. They must be reviewed after the rewrite, but real-secret fingerprints must not remain merely to make CI green.

### Status

- working-tree secret protection: **PASS** in the existing CI configuration when its Gitleaks job succeeds.
- historical scan without known-secret fingerprints: **FAIL** until history is rewritten.
- historical secret purge: **NOT_TESTED** on this branch. The GitHub API connector used for this work cannot safely run `git filter-repo` across every branch/tag and force-publish the rewritten object graph.
- credential rotation: **NOT_TESTED**. Repository access does not imply access to the external provider/account holding the active credential.

A history rewrite must be performed only after preserving this report and a mirror backup. Use `scripts/preparer_purge_secrets.py` plus `git filter-repo --replace-text`, verify all refs/tags, run Gitleaks without the historical fingerprints, then force-publish branches and tags. Rotation remains mandatory independently of rewriting.

## 2. Connector validation

ARENA's connector base class performs permission evaluation before health/authentication/network execution and queues confirmation-required writes before execution. This is the correct architectural boundary, but offline mocks are not counted as real-provider validation.

The first sensitive set for real validation is Gmail, Google Calendar, GitHub and Agent Reach. See `docs/CONNECTOR_VALIDATION.md`. Additional declared connectors must be added to the matrix as the inventory is completed; absence from the matrix means **NOT_TESTED**, not PASS.

## 3. Permissions

Expected path: agent → registry/tool → `Connecteur.executer` → `ControleAcces.verifier` → confirmation queue when required → health/authentication → connector implementation → external service.

Directly invoking `_executer` is an internal implementation detail and must never be exposed as a user/tool entrypoint. Production validation must include denial tests proving that rejected/insufficient permissions cause zero external calls.

## 4. Confidentiality

The model router has a dedicated confidentiality classifier/router and the repository documents the invariant that sensitive material stays local. This audit does **not** upgrade that statement to a real-cloud PASS until an interception test proves that a `TRES_SENSIBLE` payload never reaches Groq, DeepInfra, Anthropic, or another remote provider.

Current result: **NOT_TESTED** for the requested real-call interception proof.

## 5. Results

| Control | Result |
|---|---|
| Known active secret in current tracked files | PASS (subject to CI Gitleaks) |
| Historical real secrets absent from all Git refs | FAIL |
| Rotation independently verified | NOT_TESTED |
| Gitleaks working tree | PASS when current CI succeeds |
| Gitleaks history with no real-secret ignore fingerprints | FAIL |
| Offline connector contracts | PASS |
| Real connector authentication | SKIPPED |
| Real connector read | SKIPPED |
| Permission boundary | PASS offline; real-provider proof NOT_TESTED |
| TRES_SENSIBLE blocked before cloud transport | NOT_TESTED |
| Full regression suite | NOT_TESTED on this audit branch until CI runs |

## 6. Remaining manual/external actions

1. Rotate the surviving ARENA API credential unless provider/deployment evidence proves the historical value was already revoked.
2. Make a mirror backup, run the existing purge preparer on a full clone, execute `git filter-repo`, scan working tree and full history with Gitleaks, then force-publish all rewritten branches/tags.
3. Ask GitHub support for cached/unreachable-object cleanup if required after the force rewrite; clones/forks made before the rewrite cannot be remotely erased.
4. Configure CI secrets/test accounts for Gmail/Google OAuth and GitHub, plus any other sensitive connector selected for real validation.
5. Run real connector tests only against read-only APIs or explicit sandboxes. Missing credentials/services remain SKIPPED.

This document deliberately does not claim that the repository is fully secure or that all connectors are validated.