# GitHub Actions

## Workflow structure
- One job per concern (lint, tests, build, deploy) rather than one giant
  job that does everything sequentially — an independent failure (e.g. a
  flaky test) should not hide whether the build itself is broken, and
  independent jobs can run in parallel.
- Pin action versions to a commit SHA or a specific tag, not a floating
  major-version tag you don't control the update cadence of, for anything
  security-sensitive (checkout, secrets handling).

## Secrets
- Secrets are read from `secrets.*`/environment variables the runner
  injects, never hardcoded in the workflow file or a script it calls —
  a secret scanner (this codebase runs `gitleaks` in its own `Secret scan`
  job) exists precisely to catch the mistake, not to be a formality.
- A secret used in a `pull_request` (not `pull_request_target`) workflow
  from a fork is not available by default — this is a GitHub security
  boundary, not a bug to route around.

## Caching and speed
- Cache what is expensive to regenerate and safe to reuse (dependency
  downloads keyed by lockfile hash) — never cache something that must be
  freshly built every run (the application artifact itself, when
  correctness depends on today's source).

## Reliability
- A red run on the base branch is a real failure until proven otherwise —
  compare against the base branch's own latest run before assuming a
  red check is caused by the current change (this codebase's own
  `git-workflow.md` step 2 makes exactly this check explicit).
- Distinguish a genuine flake (died before any test body ran, or passed
  moments ago on the identical commit) from a real failure — re-running a
  job is a diagnostic step, never a way to make a real failure disappear.
