# BUG-005 — Stale `BookingHold` rows can block valid bookings indefinitely

- **Severity:** 🔴 Bug
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` §B5
- **Files:** `reservations/migrations/0002_postgres_exclude_constraints.py:23–29`,
  the hold-sweeper Celery task

## Problem

The Postgres exclusion gates on `released_at IS NULL`, not
`expires_at > now()` — Postgres won't allow `now()` in an index
predicate. The application sweeps expired holds and sets `released_at`.
If the sweeper is paused (Celery beat down, queue backed up, rolled-back
deploy), expired-but-unreleased holds remain blocking; properties become
un-bookable until someone notices.

## Proposed fix

Two options, choose one:

1. **Materialise `is_active` via a trigger** — a `BEFORE INSERT/UPDATE`
   trigger that sets `is_active = (released_at IS NULL AND expires_at >
   transaction_timestamp())`. Gate the exclusion on `is_active`. Sweeper
   becomes belt-and-braces (still useful for cleanup of historical rows)
   rather than load-bearing.
2. **Accept the risk + alert** — add a Sentry / health-check on
   "oldest-unswept-expired-hold > N minutes" and pin a hard SLA on the
   sweeper. Cheaper, but doesn't fix the underlying invariant.

Recommendation: option 1. The trigger is a one-time cost; the operational
burden of option 2 is forever.

## Acceptance

- Integration test creates an expired hold, attempts to book the same
  property/dates, succeeds (today this fails until the sweeper runs).
- Existing hold tests continue to pass.

## Dependencies

None.
