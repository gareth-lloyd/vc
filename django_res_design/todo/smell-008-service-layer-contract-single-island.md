# SMELL-008 — The service-layer contract is fully implemented in exactly one file

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `django_res/CLAUDE.md` (conventions: permission checks,
  `log_operation`, `idempotency_key`), `payments/services/refund.py`,
  the 32 modules under `*/services/`

## Problem

`django_res/CLAUDE.md` documents a three-part contract for state-mutating
services — `actor` + `actor_has_perm`, `log_operation` triples, optional
`idempotency_key` — and names `refund.py` as the reference. Adoption across
the 32 service modules:

- `actor_has_perm`: 2 files (`payments/services/refund.py`,
  `reservations/services/service_coverage.py`).
- `log_operation`: 1 file (`refund.py`).
- `idempotency_key`: 4 runtime adopters (`refund.py`, `owner_block.py`,
  `ical_ingest.py`, `comms/services.py`).

Money paths — `security_deposit.py`, `bookings.py`, `quotations.py`,
`holds.py` — implement none of it. The convention reads as established
practice but is a single island; every reviewer and agent has to guess
whether new code must comply.

## Proposed fix

Decide: aspiration (document the contract as "target state, adopt when
touching a service") vs backfill. If backfilling, do money paths first:
`security_deposit.py` (with BUG-011), `bookings.py`, `quotations.py`,
`holds.py`. Either way, update `django_res/CLAUDE.md` so the stated
convention matches reality — e.g. mark which parts are mandatory for *new*
money-path services vs opportunistic elsewhere.

## Acceptance

- A recorded decision (CLAUDE.md edit) + tickets/commits for whichever
  backfill slice is chosen.
- No service convention in CLAUDE.md that the codebase contradicts
  silently.

## Dependencies

Related: SMELL-010 (error-signalling convergence — same files, do
together), BUG-011 (the SD slice), FG-012 (`_track_payments` bypasses the
contract entirely).
