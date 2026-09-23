# Agnes video in ARENA

Agnes is integrated as a **video provider**, not as a second ARENA orchestrator.

## Runtime boundary

- `tools.video.AgnesVideoProvider` owns the HTTP contract with the separately self-hosted Agnes service.
- `tools.video.ArenaVideoOrchestrator` maps Agnes workflows (`simple`, `creative`, `manuscript`, `poetry`, `anchor`).
- `agents.video.AgnesProductionBridge` is the production-facing ARENA capability.
- Submission returns a real Agnes task id. It does **not** invent an output path.
- Collection writes only under ARENA's rendered-media directory and only after Agnes reports completion.
- Provider availability is measured through the Agnes API; unavailable infrastructure is reported, never simulated.

## Composition

The bridge can run alone for an Agnes-only request. Its collected artifact can then be handed to ARENA's existing transcription, montage, subtitle, dubbing, analysis, character, or other video tooling in a later confirmed production step.

Agnes must not become a nested autonomous planner. ARENA remains the single owner of cross-tool planning, permissions, confirmation, journaling, retries, and final artifact provenance.

## Configuration

Set `AGNES_VIDEO_URL` to the self-hosted Agnes service URL. If omitted, the adapter uses `http://127.0.0.1:8765`.

A configured URL does not prove that Agnes is running. Use the bridge/provider health result for that.
