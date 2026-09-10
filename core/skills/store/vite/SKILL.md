# Vite

## Config
- Plugins are ordered deliberately — a framework plugin (React, Vue)
  usually needs to run before a CSS/asset plugin that transforms its
  output; check an existing working config before reordering.
- Environment variables exposed to client code must be prefixed
  (`VITE_...` by default) — anything without the prefix is a server/build
  secret that Vite will NOT inline, by design. Do not "fix" a missing
  value by removing the prefix requirement.

## Build
- `import.meta.env.MODE`/`DEV`/`PROD` decide environment-specific behavior
  — never a hand-rolled `process.env.NODE_ENV` check left over from a
  webpack-era codebase.
- A single-file build target (`vite-plugin-singlefile`, used in this
  codebase's `apps/pwa/`) changes what "the build" means: verify the
  actual built artifact, not just that `vite build` exits 0 — a plugin
  interaction can silently produce an empty or broken bundle while the
  build step itself reports success.

## Dev server
- Hot module replacement expects components to be resilient to remount;
  a bug that "only happens after a hot reload" is almost always a real bug
  that a full page load would also eventually hit.

## Testing
- Vitest shares Vite's config and transform pipeline — a test failing only
  under Vitest but not in the built app (or vice versa) usually points to
  an environment/mock difference, not a tooling bug.
