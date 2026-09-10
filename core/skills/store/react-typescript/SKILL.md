# React + TypeScript (component conventions)

## Component shape
- Functional components only, typed props via an explicit `interface` or
  `type`, never `any` for a prop that has a known shape.
- Keep a component's own state minimal; derive what can be computed from
  props/state instead of storing it a second time (a duplicated value that
  can drift out of sync is a recurring source of bugs in this shape).
- Side effects (`useEffect`) declare their real dependencies. A missing
  dependency that "works anyway" today is a bug waiting for the next
  refactor — trust the linter's exhaustive-deps rule over instinct.

## State
- Local state (`useState`) for what only this component cares about.
- Shared state (a store — Zustand in this codebase's `apps/pwa/`, see
  `package.json`) only for what multiple components genuinely need to
  read or write together. Promoting local state to a shared store
  "just in case" adds an indirection with no present benefit.

## Errors and loading
- Every data-fetching component has three visible states, not one: loading,
  error, and empty — not just the happy path with data. A screen that only
  renders correctly when the network is fast and never fails is untested
  in the state that matters most to a real user.

## Testing
- Test behavior (what the user can do, what renders) over implementation
  details (internal state shape, private function names).
- A snapshot test that nobody reads on failure is not a regression guard —
  prefer explicit assertions on rendered content/roles.

## Accessibility
- Every interactive element is reachable by keyboard and has an accessible
  name — a `<div onClick>` styled as a button is not a button.
