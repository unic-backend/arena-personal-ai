# Playwright

## Locators
- Prefer role/accessible-name locators (`getByRole`, `getByLabel`,
  `getByText`) over CSS selectors tied to implementation details (a class
  name, a DOM nesting path) — the former survive a restyle, the latter
  break on one.
- A locator that matches more than one element is a real test bug, not
  something to silence with `.first()` by default — check whether the
  page genuinely has a duplicate, or the locator is simply too broad.

## Waiting
- Never add a fixed `page.waitForTimeout(...)` to work around flakiness —
  it hides the real race condition and makes the test both slower and
  still unreliable under different load. Wait for the actual condition
  (`waitForResponse`, an element becoming visible, a network request
  settling) instead.
- Playwright's own auto-waiting (on actionability: visible, enabled,
  stable) handles most of what a manual wait was trying to work around —
  a flaky click is usually solved by waiting for the right state, not a
  longer sleep.

## Test isolation
- Each test starts from a known state (a fresh context/page, seeded data)
  — a test that depends on a previous test having run first is not
  actually testing what it claims to, and will fail unpredictably when
  run alone or reordered.
- Network calls to real external/third-party services are mocked or
  routed (`page.route`) in a test that is meant to verify the app's own
  logic — a test that fails because an unrelated third party is down is
  not telling you anything about a regression in this codebase.

## Debugging a failing test
- Reproduce locally with the trace/video artifacts Playwright can record
  before guessing at a fix — a screenshot at the point of failure usually
  answers "what did the page actually look like" faster than re-reading
  the test code.
