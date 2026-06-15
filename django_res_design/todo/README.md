# Villa Collective — Todo / Tickets

Tracked work items derived from the design package and recent audits. Each
file is one ticket. Filenames encode `<bucket>-<id>-<short-slug>.md`.

## Buckets

- **`bug-*`** — schema or service allows invalid state today. Source:
  the 2026-05-26 data-model deep audit (🔴 Bugs).
- **`fg-*`** — footguns. Correct only if callers are careful; nothing
  enforces it. Source: same audit (🟠 Footguns).
- **`smell-*`** — works today, will hurt later. Same audit (🟡 Smells).
- **`q-*`** — open product questions from `product-design/06-verification.md`
  that block a slice of implementation until answered.
- **`gap-*`** — designed-but-unbuilt surface area (empty URL files,
  uncovered endpoint sets, frontend placeholders).
- **`inv-*`** — investigations the audit flagged as "noticed but didn't
  fully chase". Each becomes a ticket if it turns up a real issue.

## Layout & status

- **Open tickets** live flat in this directory.
- **Resolved / dropped tickets** live in [`done/`](done/); each carries a
  top-of-file `✅ RESOLVED` / `❌ DROPPED` banner stating the problem, the
  fix, and the commit. The detailed original body is preserved below the
  banner for context.
- [`INDEX.md`](INDEX.md) is the live dashboard — open work at the top, a
  resolved/dropped reference at the bottom. It is the source of truth for
  status; the per-file banners record *how* each ticket was closed.

The original audit's "fix first" sequence (the cheap constraint bugs, the
reference-generation races, the booking row-lock work) is now entirely in
`done/`. Remaining open work has no strict order — start from the
"Decisions blocking implementation" list in `INDEX.md`, then the hygiene
tier; the rest are handled the next time their app is touched.

## Conventions

Each ticket has:

- **Severity** — bug / footgun / smell / question / gap.
- **Source** — pointer to the design doc that surfaced it.
- **Files touched** — best-guess file:line references.
- **Problem** — what's wrong.
- **Proposed fix** — concrete approach.
- **Acceptance** — how we'll know it's done (tests, constraints, etc.).
- **Dependencies** — other tickets this blocks or is blocked by.

When a ticket is merged, prepend a `✅ RESOLVED` banner (problem / fix /
commit), `git mv` the file into `done/`, and update its row in `INDEX.md`.
