> **✅ RESOLVED (2026-06-15)** — Problem: Idempotency used check-then-create with no DB backstop, allowing races. Fix: Added partial unique indexes plus an over-refund lock as a DB backstop. Commit: 3f628f1.
>
> _Original ticket preserved below for context._

# FG-010 — Idempotency is check-then-create with no DB backstop

- **Status:** ✅ Resolved
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

## Resolution

All three races now have a DB (or lock) floor:

1. **Meta-key pattern** — partial unique indexes backstop both adopters of
   `find_by_meta_key`:
   `refund_idempotency_key_unique_per_booking` on
   `(booking, meta->>'idempotency_key')` and
   `payment_idempotency_key_unique_per_booking_purpose` on
   `(booking, purpose, meta->>'idempotency_key')` — each scoped exactly to
   the queryset its service pre-checks (`RefundService.request`,
   `ManualPaymentService.record` from FG-012). The losing concurrent racer
   now fails loudly with `IntegrityError` instead of silently duplicating
   (migration `payments/0008`). The outbound-refund `Payment` minted by
   `execute` carries only `meta['refund_id']`, so the constraint doesn't
   touch it; `execute` is already serialised by `refresh_locked` (FG-006
   pattern).
2. **`Booking.quotation_line`** — already floored by the unconditional
   `booking_one_per_quotation_line` UniqueConstraint
   (`reservations/0029`, landed with the POST /bookings lifecycle-bypass
   fix, `51760f9`) and pinned by
   `test_second_booking_on_same_quotation_line_is_refused`. No
   non-cancelled scoping: one line = one booking, full stop (rebooking a
   cancelled stay goes through a fresh quotation line).
3. **Over-refund aggregate** — `RefundService.request` now takes
   `SELECT … FOR UPDATE` on `against_payment` before the `Sum("amount")`
   check, so a second concurrent partial refund serialises behind the
   first's commit and its aggregate sees the committed total.

The `core/idempotency.py` docstring no longer claims transactional
collapse; it now documents the DB-backstop requirement for every adopting
model and points at the three reference constraints. Tests:
`test_request__duplicate_idempotency_key_hits_db_backstop`,
`test_request__locks_against_payment_before_over_refund_check`
(`payments/tests/test_refund.py`),
`test_duplicate_key_same_booking_and_purpose_hits_db_backstop`
(`payments/tests/test_manual_payment_service.py`).

**Post-resolution review follow-up (2026-06-12):** a code review found the
refund API surface had not been wired to the fix —
`RefundRequestSerializer` didn't accept `idempotency_key` (making the
service's idempotency support dead code on `POST /bookings/{id}/refunds`),
and the view let the backstop's `IntegrityError` surface as a 500. Closed by
exposing an optional `idempotency_key` on the serializer (mirroring
`ManualPaymentCreateSerializer`) and mapping the race `IntegrityError` to a
409 `invalid_state` DomainError in `request_refund_for_booking`, matching
`_service_call` in `payments/views/track.py`. Tests:
`test_request_refund__retry_with_same_idempotency_key_returns_original`,
`test_request_refund__idempotency_race_returns_409_not_500`
(`payments/tests/test_api_refunds.py`).
