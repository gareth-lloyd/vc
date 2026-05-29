# BUG-001 — `CANCELLED` status must imply `cancelled_at IS NOT NULL`

- **Severity:** 🔴 Bug
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` §B1
- **Files:** `reservations/models/booking.py:151–152`

## Problem

The existing `booking_cancelled_at_implies_cancelled_status` constraint is
one-directional: `cancelled_at IS NOT NULL → status = CANCELLED`. The
inverse is not enforced. The schema today permits
`status=CANCELLED, cancelled_at=NULL` — a cancelled booking with no
cancellation timestamp.

`Booking.cancel()` sets both, but `update_or_create`, bulk updates, the
legacy importer, and the admin can land an invalid row.

## Proposed fix

Add the inverse `CheckConstraint`:

```python
CheckConstraint(
    condition=Q(cancelled_at__isnull=False) | ~Q(status=BookingStatus.CANCELLED.value),
    name="booking_cancelled_status_requires_cancelled_at",
)
```

Migration: new `CheckConstraint` add — no data migration needed unless the
production DB already contains violators (run `reconcile_legacy` /
ad-hoc query to confirm before merging).

## Acceptance

- New constraint present and named.
- Regression test in `reservations/tests/` asserts an `IntegrityError`
  when forcing `status=CANCELLED, cancelled_at=NULL` via raw SQL or
  `update_fields`.
- Existing booking-cancel tests still pass.

## Dependencies

None.
