> **❌ DROPPED (2026-06-18)** — Problem: legacy let staff overwrite
> `VillaBooking.RentalPrice` directly; the rebuild has no equivalent override.
> Fix: superseded by the signed charge-line. `BookingChargeItem` (e.g.
> "Negotiated rate adjustment −400.00") already covers the operator need and is
> *better* than a silent edit — the label records the *why*, and the write
> resyncs the deposit/balance schedule and any pre-charge security deposit (the
> `booking_total_changed` chain, GAP-015/GAP-019). No new `:override-price`
> action; re-open only if ops require a true rental-figure override (e.g. a
> re-priced engine total) the charge line can't express.
>
> _Original ticket preserved below for context._

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
