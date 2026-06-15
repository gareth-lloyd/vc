> **✅ RESOLVED (2026-06-15)** — Problem: modify_dates/modify_guests re-ran pricing without row locks, risking concurrent-write desync. Fix: Added a row lock and reload around the modify paths.
>
> _Original ticket preserved below for context._

# FG-006 — `Booking.modify_dates` / `modify_guests` re-run pricing without row locks

- **Severity:** 🟠 Footgun
- **Source:** the 2026-05-26 data-model deep audit §F6
- **Files:** `reservations/models/booking.py:387–493`

## Problem

Both methods wrap their work in `@transaction.atomic`, but neither takes
a `select_for_update()` on the Booking row. Two parallel "modify dates"
requests can interleave:

- T1 reads dates
- T2 writes new dates and commits
- T1 reruns pricing from its read of dates
- T1 writes — overwriting T2's dates with stale pricing.

Postgres' default `READ COMMITTED` isolation does not save you.

## Proposed fix

Start each transaction by re-fetching with a row lock:

```python
@transaction.atomic
def modify_dates(self, ..., *, actor=None):
    booking = (
        Booking.objects
        .select_for_update()
        .get(pk=self.pk)
    )
    # …operate on `booking`, not `self`…
```

The pattern should be applied to any service that recomputes derived
state from instance fields under contention. Consider extracting a
service-layer helper to avoid repeating it.

## Acceptance

- Both `modify_dates` and `modify_guests` take a `SELECT … FOR UPDATE`
  on the Booking row.
- Regression test (using two threads / `transaction.atomic` blocks)
  that today flakes/loses-writes now serialises cleanly.

## Resolution

✅ Added `Booking._lock_for_update()` (`reservations/models/booking.py`) — takes
`SELECT … FOR UPDATE` on the row then `refresh_from_db()` — and call it as the
first statement inside both `modify_dates` and `modify_guests` (both already
`@transaction.atomic`). The lock serialises a second concurrent caller behind
the first; the reload makes `self` reflect the committed state before re-pricing,
so the later writer can't clobber the earlier with stale data.

Regression tests in `reservations/tests/test_booking.py`
(`test_modify_dates_reloads_committed_state_before_repricing`,
`test_modify_guests_reloads_committed_state_before_repricing`) reproduce the
lost-update window single-threaded: a stale handle is loaded, a second handle
commits a change, then the stale handle modifies — the event's `from` must reflect
the committed value, not the stale one. Both fail without the lock helper. A
threaded `transaction=True` variant was dropped in favour of the deterministic
single-threaded form (the threaded version raced its own DB teardown and
destabilised the rest of the suite).

## Dependencies

None.
