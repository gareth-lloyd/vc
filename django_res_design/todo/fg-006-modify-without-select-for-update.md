# FG-006 — `Booking.modify_dates` / `modify_guests` re-run pricing without row locks

- **Severity:** 🟠 Footgun
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` §F6
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

## Dependencies

None.
