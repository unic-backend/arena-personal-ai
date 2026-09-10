# Tailwind CSS

## Tokens over raw values
- Prefer the design tokens already configured (`tailwind.config.*`,
  CSS custom properties) over a raw hex color or an arbitrary pixel value
  in a class — `bg-brand` survives a rebrand, `bg-[#3b82f6]` does not.
- An arbitrary-value class (`w-[137px]`) is a signal the design system is
  missing a token, not a convenient shortcut to reach for by default.

## Responsive and state variants
- Mobile-first: the unprefixed class is the smallest breakpoint, `sm:`/
  `md:`/`lg:` layer on top — never the reverse.
- Group related state variants next to the base utility they modify
  (`hover:`, `focus-visible:`, `disabled:`) so the full behavior of one
  property reads in one place, not scattered across the class list.

## Consistency
- Reuse existing component classes/utility combinations already in the
  codebase before inventing a new one that does the same thing slightly
  differently — a spacing scale is only useful if nothing bypasses it.
- Dark mode (if configured) is handled through the same token system, not
  a second set of hardcoded colors guarded by a `dark:` prefix everywhere.

## Accessibility
- Color alone never carries meaning (an error state needs an icon or text,
  not just a red border) — a contrast check belongs in the same review as
  a color choice, not a follow-up.
