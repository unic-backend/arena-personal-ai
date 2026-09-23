# Video production reachability — 2026-09-23

## Finding

The old note in `docs/CURRENT_TASK.md` saying `/api/video/projet` is reachable only by direct HTTP is stale.

The current production path is already wired end to end:

1. `agents/orchestrator/orchestrator_agent.py` declares `VIDEO_PROJET` as a valid intent and includes it in the `video` PWA space family.
2. Explicit full-production phrases are recognized by the deterministic `VIDEO_PROJET` vocabulary before single-purpose video routes can capture them.
3. `apps/backend/routers/pwa_gateway.py` imports and uses the shared `dispatch_request` chat dispatcher.
4. `apps/backend/routers/chat.py::_aiguiller` handles `VIDEO_PROJET` and calls the real `video_production_agent.run(...)`.
5. References are built server-side from `medias_montables(...)`; the model does not invent filesystem paths.
6. The dedicated `/api/video/projet` route remains available for direct API clients, status, resume and cancellation.

## Regression guard

`tests/test_video_chat_reachability.py` locks the three architectural links that make the feature reachable from the user-facing PWA/chat path.

## Important distinction

Reachable does not mean every external generator is locally installed or online. Runtime availability remains governed by the existing provider/connector availability checks and configuration. Missing external engines must continue to report `NOT_CONFIGURED`/unavailable rather than being simulated.
