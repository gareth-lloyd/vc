> **✅ RESOLVED (2026-06-15)** — Problem: Booking and quotation-line currencies could drift apart. Fix: Resolved via GAP-014: a per-line currency invariant enforced at write time.
>
> _Original ticket preserved below for context._

# FG-001 — `Booking` and quotation-line currencies are independent

- **Severity:** 🟠 Footgun — **largely resolved by GAP-014** (see below)
- **Source:** the 2026-05-26 data-model deep audit §F1; re-scoped 2026-06-10 by
  [GAP-014](gap-014-quote-currency-forced-selection.md)
- **Files:** `reservations/models/booking.py` (`currency`, `modify_dates`),
  `reservations/models/quotation.py` (`QuotationLine.currency`),
  `reservations/services/bookings.py` (`create_from_quotation_line`)

## Problem (as re-scoped)

The original ticket anchored the invariant on the **header** `Quotation.currency`.
GAP-014 removed that field: currency now lives per line
(`QuotationLine.currency`, legacy parity), so the invariant is

> `Booking.currency == source QuotationLine.currency`

**Status:** enforced at write time — `BookingService.create_from_quotation_line`
copies `quotation_line.currency` onto the Booking, pinned by
`test_create_from_quotation_line_carries_line_currency`
(`reservations/tests/test_booking_service.py`). A quotation's options can mix
currencies; the accepted line's currency is what the guest pays in.

`Booking.modify_dates` / `modify_guests` re-run pricing with an **explicit**
`currency=self.currency`, and the engine exact-matches it (no FX): if the
property's rate-plan currency has switched since confirmation, the recompute
raises `NoRateAvailable` — a loud failure, not a silently re-denominated
`balance_due`.

## Remaining (optional) hardening

- A DB-level expression of the invariant would require denormalising
  `line_currency_id` onto Booking purely for a CheckConstraint — judged not
  worth the duplicate column while the single write path + test hold the line.
  Revisit if a second Booking-creation path appears.

## Acceptance

- ✅ Booking-from-line carries the line's currency (test above).
- ✅ Engine exact-match means a modify-dates recompute can never come back in
  a different currency than `self.currency`.

## Dependencies

- [GAP-014](gap-014-quote-currency-forced-selection.md) — the re-scoping
  change (per-line currency, header dropped).
