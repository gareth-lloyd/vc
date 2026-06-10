# FG-010 — Idempotency is check-then-create with no DB backstop

- **Severity:** 🟠 Footgun
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `core/idempotency.py:10–12,35–50`,
  `reservations/models/booking.py:105–110`,
  `payments/services/refund.py:84–111`

## Problem

Three related races, none floored by the database:

1. `find_by_meta_key` is a plain check-then-create. The module docstring
   claims the lookup runs "*under the same transaction so we collapse
   concurrent retries*" — under READ COMMITTED that is simply false: two
   concurrent calls both see no row and both create.
2. `Booking.quotation_line` is a plain `ForeignKey(..., on_delete=PROTECT)`
   despite being the documented natural idempotency key for
   `BookingService.create_from_quotation_line` — nothing stops two
   concurrent conversions creating two bookings off one line.
3. `RefundService.request`'s over-refund check aggregates
   `Sum("amount")` over existing refunds (refund.py:99–111) without locking
   `against_payment` — two concurrent partial refunds can jointly exceed the
   original payment.

## Proposed fix

- Add DB backstops: a conditional `UniqueConstraint` on
  `Booking.quotation_line` (scoped to non-cancelled statuses if rebooking a
  cancelled line must stay legal); `select_for_update()` on
  `against_payment` (or the booking row) before the over-refund aggregate.
- For the meta-key path, either a partial unique index on
  `(booking, meta->>'idempotency_key')` per adopting model, or promote the
  key to a dedicated column + `UniqueConstraint` (the docstring already
  anticipates this for models without `meta`).
- Correct the `core/idempotency.py` docstring either way — it must not
  promise concurrency safety the implementation doesn't have.

## Acceptance

- Migration adds the constraints; tests assert `IntegrityError` on a
  duplicate booking-per-line and that a second `request()` inside the
  locked window cannot over-refund.
- Docstring no longer claims transactional collapse without the backstop.

## Dependencies

None. Related: FG-006 (resolved) established the `select_for_update`
pattern on booking transitions.
