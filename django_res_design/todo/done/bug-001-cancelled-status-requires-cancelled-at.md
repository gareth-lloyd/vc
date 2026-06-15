> **✅ RESOLVED (2026-06-15)** — Problem: A Booking with CANCELLED status could have cancelled_at left NULL, so the status and timestamp could disagree. Fix: Added an invariant so CANCELLED status implies cancelled_at IS NOT NULL.
>
> _Original ticket preserved below for context._

# BUG-001 — `CANCELLED` status must imply `cancelled_at IS NOT NULL`

- **Severity:** 🔴 Bug
- **Source:** the 2026-05-26 data-model deep audit §B1
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

## Resolution

✅ Added inverse `CheckConstraint` `booking_cancelled_status_requires_cancelled_at`
(`cancelled_at IS NOT NULL OR status != CANCELLED`) in
`reservations/models/booking.py`; migration `reservations/0009`. The legacy
`BookingLoader` always lands DRAFT, so no data migration was needed.

The constraint surfaced three pre-existing test fixtures that fabricated
`status=CANCELLED, cancelled_at=NULL` directly (bypassing `cancel()`):
`test_restore_reverses_archive` now goes through `booking.cancel()`, and the
`_make_booking` / terminal-status helpers in
`pricing/tests/test_availability_service.py`,
`reservations/tests/test_api_bookings.py`, and
`payments/tests/test_payment_reminders.py` now stamp `cancelled_at`. Regression
test `test_cancelled_status_requires_cancelled_at` in
`reservations/tests/test_booking.py`.
