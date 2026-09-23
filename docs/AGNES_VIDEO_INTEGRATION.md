# Agnes video in ARENA

Agnes is integrated as a **video provider**, not as a second ARENA orchestrator.

## Runtime boundary

- `tools.video.AgnesVideoProvider` owns the HTTP contract with the separately self-hosted Agnes service.
- `tools.video.ArenaVideoOrchestrator` maps Agnes workflows (`simple`, `creative`, `manuscript`, `poetry`, `anchor`).
- `tools.video.AgnesProductionBridge` is the thin production-facing wrapper around the HTTP contract — **not**, contrary to what this file claimed until 2026-09-23, importable from `agents.video` (`agents/video/__init__.py` is empty; that import raises `ImportError`).
- `core/connectors/agnes.py::AgnesConnector` is the actual ARENA production boundary (DEC-0132): it is the piece registered in `apps/backend/runtime.py`'s connector registry and reachable from a real chat request. It wraps `AgnesProductionBridge`, adds the confirmation gate (`video_generation.generate = CONFIRMATION`, same service as WanGP/MoneyPrinterTurbo/HiDream-I1/Xaar Kaname — no new permission section), and re-verifies a "completed" task by actually collecting the file before reporting success (never trusting the provider's own "done" claim, same discipline as HiDream/Xaar Kaname).
- `agents/video/production_agent.py::VideoProductionAgent` is the orchestrator that can compose an `"agnes"` step in a project graph (`core/production/plan_video.py::CAPACITES_VIDEO`), alongside `wangp`/`moneyprinter`/`hidream_image`/etc.
- Submission returns a real Agnes task id. It does **not** invent an output path.
- Collection writes only under ARENA's rendered-media directory and only after Agnes reports completion.
- Provider availability is measured through the Agnes API; unavailable infrastructure is reported, never simulated.

**Measured 2026-09-23**: before `AgnesConnector` existed, `AgnesProductionBridge` was real, tested code (twenty test files) that no production path could reach — `grep -i agnes` across `apps/backend/`, `agents/` (outside `tools/video/__init__.py` itself), and `core/connectors/registre.py` returned nothing. `scripts/orphelins.py` reported it as reachable only because it lives in the same file as `FFmpegTool`, which genuinely is imported — the scanner measures at file granularity, not per-class. This file's own claimed import path was one of the symptoms.

## Composition

The bridge can run alone for an Agnes-only request. Its collected artifact can then be handed to ARENA's existing transcription, montage, subtitle, dubbing, analysis, character, or other video tooling in a later confirmed production step.

Agnes must not become a nested autonomous planner. ARENA remains the single owner of cross-tool planning, permissions, confirmation, journaling, retries, and final artifact provenance. This is why `AgnesConnector` never exposes Agnes's own `pipeline` mode.

## Configuration

Set `AGNES_VIDEO_URL` to the self-hosted Agnes service URL. If omitted, the adapter uses `http://127.0.0.1:8765`.

A configured URL does not prove that Agnes is running. Use the bridge/provider health result for that.
