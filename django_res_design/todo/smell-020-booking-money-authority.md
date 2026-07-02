# SMELL-020 — Booking has no single money authority; the guest total is re-derived byte-for-byte in two apps

- **Severity:** 🟡 Smell
- **Source:** the 2026-07-02 backend complexity audit (money-model fragmentation)
- **Files:** `reservations/models/booking.py:132–137`,
  `reservations/services/concierge.py:32–66`,
  `reservations/signals.py:133–141` (+ `149–152`),
  `reservations/services/charges.py:81–103`,
  `payments/services/payment_scheduler.py` (`_booking_total`)

## Problem

"How much does this booking cost the guest?" has no single answer in code.
The money is spread across four `Booking` columns plus a JSON snapshot plus
two independent child-line types, and the two children are kept in sync by
**two different, incompatible denorm strategies**:

- `Booking` carries `rental_price`, `discount`, `adjustment`, `balance_due`
  **and** `pricing_snapshot` (JSON) — `booking.py:132–137`.
- `BookingChargeItem` writes fire `booking_total_changed`
  (`signals.py:149–152`) → payments resizes the schedule + the security
  deposit. Charges have **no** denorm column; the guest total is live-summed.
- `BookingConciergeItem` writes fire `_concierge_item_changed`
  (`signals.py:133–141`) → `ConciergeService.recompute_adjustment` writes the
  `Booking.adjustment` **column** (`concierge.py:56`) and does **not** fire
  `booking_total_changed`.

The dangerous part: `Booking.adjustment` is **written but never read by any
total computation**. `charges._booking_base_total` (`charges.py:81–92`) and
`booking_charge_breakdown` (`charges.py:102–103`) both build the guest total
as `pricing_snapshot["total"] + Σ charge_items` only, and each carries a
comment that it "mirrors" / "replicates `PaymentScheduler._booking_total`
byte-for-byte." So the real guest total is hand-synced across **three** call
sites (payments' scheduler + two reservations helpers), while a fourth column
(`adjustment`) moves on concierge writes and is consumed by nothing.

## Why it bites

There is no `Booking.total()`. Any new money surface — taxes, fees, the
promised concierge `Payment(purpose=CONCIERGE)` line (`concierge.py`) — has to
be threaded into three hand-synced total formulas across two apps, and the
formulas can silently drift (the "byte-for-byte" comments are the only thing
holding them together). Eventually someone reads `adjustment` assuming it is
live and ships a wrong number.

## Proposed fix

- Introduce **one** `booking_total()` (service function or model method) as
  the single money authority; point the payment scheduler, `charges`, and the
  breakdown at it so there is exactly one formula.
- Resolve the concierge denorm: either make `BookingConciergeItem` writes fire
  `booking_total_changed` like charges (so concierge money actually reaches the
  schedule/SD), or drop the dead `adjustment` column and fold concierge lines
  into the single total. Pick one — the current split is the smell.

Behaviour-preserving for the GROSS/charges path; the concierge decision is the
one product-visible choice (does concierge money resize the payment schedule?).

## Acceptance

- A single `booking_total()` is the only place the guest grand total is
  computed; `payment_scheduler`, `charges`, and `booking_charge_breakdown`
  delegate to it (no duplicated "mirrors … byte-for-byte" formulas).
- Test: adding a concierge line changes `booking_total()` **and** whatever it
  is contracted to drive (schedule/SD, or explicitly documented as
  non-scheduling); `adjustment` is either live-and-read or gone.
- No call site reads `Booking.adjustment` as an authoritative total unless it
  is proven live.

## Dependencies

Builds on FG-011 (`adjustment` recompute skips bulk paths — same column).
Related: SMELL-008 (service-layer contract). Touches the same payments
signal chain as SMELL-021 / GAP-061.
