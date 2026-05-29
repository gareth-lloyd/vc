# Villa Collective — Todo / Tickets

Tracked work items derived from the design package and recent audits. Each
file is one ticket. Filenames encode `<bucket>-<id>-<short-slug>.md`.

## Buckets

- **`bug-*`** — schema or service allows invalid state today. Source:
  `findings/2026-05-26-data-model-deep-audit.md` (🔴 Bugs).
- **`fg-*`** — footguns. Correct only if callers are careful; nothing
  enforces it. Source: same audit (🟠 Footguns).
- **`smell-*`** — works today, will hurt later. Same audit (🟡 Smells).
- **`q-*`** — open product questions from `product-design/06-verification.md`
  that block a slice of implementation until answered.
- **`gap-*`** — designed-but-unbuilt surface area (empty URL files,
  uncovered endpoint sets, frontend placeholders).
- **`inv-*`** — investigations the audit flagged as "noticed but didn't
  fully chase". Each becomes a ticket if it turns up a real issue.

## Priority order (from audit's "What to fix first")

The audit's recommended sequence — all are 🔴 unless noted:

1. `bug-004-owner-approval-race.md` — was B4; **already resolved**, kept as a
   reference of the fix shape.
2. `bug-007-reference-generation-races.md` — B7. Bulk-create bypass is a
   ticking bomb for the cutover.
3. `bug-006-payment-active-purpose-uniqueness.md` — B6. Security deposits
   are real money.
4. `fg-001-booking-quotation-currency-drift.md` — F1.
5. `fg-006-modify-without-select-for-update.md` — F6.
6. `bug-001-cancelled-status-requires-cancelled-at.md`,
   `bug-002-raterule-zero-length-range.md`,
   `bug-003-raterule-poa-vs-price-contradiction.md` — three-line constraint
   fixes; cheap.

After that, the rest are handled the next time their app is touched.

## Conventions

Each ticket has:

- **Severity** — bug / footgun / smell / question / gap.
- **Source** — pointer to the design doc that surfaced it.
- **Files touched** — best-guess file:line references.
- **Problem** — what's wrong.
- **Proposed fix** — concrete approach.
- **Acceptance** — how we'll know it's done (tests, constraints, etc.).
- **Dependencies** — other tickets this blocks or is blocked by.

Pick tickets in priority order unless a dependency forces a different
sequence. Move a ticket to `done/` once merged and link the commit.
