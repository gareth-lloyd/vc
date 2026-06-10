# GAP-016 — rental-price override (legacy parity remainder)

- **Severity:** Gap
- **Source:** booking-charge-items work (2026-06-10)
- **Files:** `django_res/reservations/models/booking.py`,
  `django_res/reservations/serializers/booking.py`

## Problem

Legacy staff could edit `VillaBooking.RentalPrice` directly on any active
booking. The rebuild's charge-items phase deliberately scoped this out:
`BookingChargeItem` covers labelled extras/credits, but there is no way to
override the engine-priced rental figure itself (e.g. price-match a
negotiated rate without re-running the engine).

A signed charge line can approximate it ("Negotiated rate adjustment
−400.00"), which may be good enough — the label makes the *why* explicit,
which a silent rental_price edit never did.

## Proposed fix (if wanted)

An explicit `:override-price` action (ADMIN-gated, mandatory reason) that
rewrites `rental_price`/`balance_due`, stamps a `BookingEvent` with
before/after, and triggers the schedule resync. Decide first whether the
charge-line approximation already covers the real operator need — check with
ops before building.
