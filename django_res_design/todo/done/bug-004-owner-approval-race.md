> **✅ RESOLVED (2026-06-15)** — Problem: Concurrent owner-approval actions could race and produce inconsistent approval state. Fix: Closed the owner-approval race so concurrent approvals are serialised safely.
>
> _Original ticket preserved below for context._

# BUG-004 — Owner-approval race could double-book overlapping dates

- **Severity:** 🔴 Bug — **RESOLVED**
- **Source:** the 2026-05-26 data-model deep audit §B4
- **Files:** `reservations/migrations/0007_booking_overlap_includes_pending_approval.py`,
  `reservations/models/booking.py` (`_transition`, `modify_dates`),
  `reservations/services/quotations.py` (`:convert` flow)

## Status

Resolved before this todo bucket was opened. Kept as a reference for the
shape of the fix and for confirming no regression sneaks back in.

## Resolution recap

The original `booking_no_overlap_active` Postgres exclusion gated on
`status IN (awaiting_deposit, deposit_paid, awaiting_balance, balance_paid,
checked_in)` — leaving `DRAFT` and `PENDING_OWNER_APPROVAL` open. Two
parallel approval flows could both create `PENDING_OWNER_APPROVAL` rows;
the loser exploded with an opaque `IntegrityError` when the owner finally
approved.

Migration `0007_booking_overlap_includes_pending_approval` drops the old
constraint and replaces it with `booking_no_overlap_blocking`, which
includes `pending_owner_approval` in the predicate. `_transition`,
`modify_dates`, and the `:convert` flow translate the `IntegrityError`
into `OverlappingBooking` (HTTP 409).

## Watch

- Any new "blocking" booking status must be added to the exclusion
  predicate via a fresh migration. A regression test should pin the set
  of statuses in the constraint (read the predicate via pg_catalog).
- Consider promoting the test in `reservations/tests/` to assert the
  409 → friendly-error path stays intact.

## Dependencies

None — informational ticket.
