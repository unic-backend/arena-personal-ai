# Python / FastAPI (ARENA backend conventions)

Applies to `apps/backend/` and any Python service in this shape.

## Routing
- One router per feature under `apps/backend/routers/`, mounted once in `main.py`.
- Every mutating route depends on `verify_api_key` and, where the action has
  a real-world side effect, a rate limiter (`limiter_debit`).
- A route is a thin adapter: it validates the request (Pydantic model),
  calls a connector or agent through the shared registry, and translates
  `ResultatAction` into an HTTP response. Business logic does not live in
  the route function.

## Errors and results
- Never raise a bare exception from a route handler for an expected failure
  (missing config, unreachable dependency). Return the typed result
  (`ResultatAction`/`Statut`) and let the router translate it — a `503` for
  `NOT_CONFIGURED`, a `409` for something that needs confirmation, etc.
- A capability that cannot run reports why (`ce_qui_manque`), never a
  generic 500 that hides the cause.

## Testing
- `TestClient(app, raise_server_exceptions=False)` for real HTTP-level
  tests — never call the handler function directly when the behavior under
  test is routing/dispatch, not just the handler's own logic.
- Prefer a real dependency over a mock when the dependency is cheap and
  local (SQLite, filesystem). Mock only what is genuinely external or slow
  (a paid API, a GPU model call).
- Async tests use `pytest-asyncio`; a fixture that returns a coroutine
  without `await`-ing it is a common, silent bug — assert the return type
  in at least one test per async helper.

## Pydantic
- Model fields default to `None` with `Optional[...]`, never a sentinel
  string like `"unknown"` — a missing value and a real value must never be
  representable by the same type.
- Validate at the boundary (the request model), not deep inside business
  logic — by the time a value reaches a connector, it should already be
  well-typed.
