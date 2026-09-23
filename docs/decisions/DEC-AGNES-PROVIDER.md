# Agnes as an ARENA video provider

Status: active

Agnes is a provider inside the ARENA video domain. It may execute an Agnes-only generation, and its completed artifact may be composed with other ARENA video capabilities. It is not allowed to become a second cross-tool planner.

The production boundary is `tools.video.AgnesProductionBridge`. Submission exposes the real provider task id and no fabricated file. Collection is permitted only after the provider reports completion and the destination is constrained to ARENA rendered media.

This keeps one owner for cross-tool planning and provenance: ARENA.
