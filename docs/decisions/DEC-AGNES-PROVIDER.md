# Agnes as an ARENA video provider

Status: active — see the full decision record and measurement in `docs/DECISIONS.md`, DEC-0132.

Agnes is a provider inside the ARENA video domain. It may execute an Agnes-only generation, and its completed artifact may be composed with other ARENA video capabilities. It is not allowed to become a second cross-tool planner.

`tools.video.AgnesProductionBridge` holds the HTTP contract (submission, status, collection). **The actual production boundary — the piece a real chat request reaches — is `core/connectors/agnes.py::AgnesConnector`** (DEC-0132, 2026-09-23): it is what `apps/backend/runtime.py` registers in the connector registry, what `agents/video/production_agent.py` calls through `CAPACITES_VIDEO`, and what enforces the confirmation gate (`video_generation.generate = CONFIRMATION`). Until that connector existed, this status line said "active" while nothing in the request path could reach `AgnesProductionBridge` at all — measured by `grep` and by a real `ImportError` on the path this file's sibling doc used to claim. "Status: active" now means what it says because a chat request can actually get here; it did not before.

Submission exposes the real provider task id and no fabricated file. Collection is permitted only after the provider reports completion and the destination is constrained to ARENA rendered media.

This keeps one owner for cross-tool planning and provenance: ARENA.
