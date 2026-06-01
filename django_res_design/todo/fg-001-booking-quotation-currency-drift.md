# FG-001 — `Booking` and `Quotation` currencies are independent

- **Severity:** 🟠 Footgun
- **Source:** the 2026-05-26 data-model deep audit §F1
- **Files:** `reservations/models/booking.py:63–67`,
  `reservations/models/quotation.py:42–46`,
  `reservations/services/bookings.py` (`create_from_quotation_line`),
  `reservations/models/booking.py:387–437` (`modify_dates`)

## Problem

Both `Booking` and `Quotation` hold their own `currency_id` FK. Nothing
enforces equality between a Booking and the source QuotationLine's
Quotation. `Booking.modify_dates` re-runs pricing inside
`@transaction.atomic` using `self.currency` as the snapshot input — if
the property's RatePlan currency has drifted, the recomputed
`balance_due` ends up in a different currency than the customer was
originally quoted in.

There is no "currency-locked at confirmation" invariant.

## Proposed fix

Two layers:

1. **Schema invariant.** Denormalise `quotation_currency_id` onto
   `Booking` (or reach through to the source QuotationLine via a
   constraint expression) and add a CheckConstraint that
   `currency_id == quotation_currency_id`. Easier alternative: enforce
   the equality only at write time in `BookingService` and add a test.
   Constraints win when feasible.
2. **Operational guard.** In `Booking.modify_dates` / `modify_guests`,
   assert that the pricing recompute returns an amount in
   `self.currency` and raise a typed error if not. The pricing engine
   probably already returns currency in its result — verify it does
   and add the guard.

## Acceptance

- Service-level test: creating a booking with a currency that mismatches
  its quotation raises a domain error.
- Modify-dates test: forcing a currency mismatch in the recompute raises
  rather than silently corrupting `balance_due`.

## Dependencies

None.
