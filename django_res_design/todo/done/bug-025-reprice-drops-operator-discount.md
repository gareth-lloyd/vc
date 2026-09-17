# BUG-025 — Repricing a booking silently restores the undiscounted price

> **✅ RESOLVED (2026-09-17, local `main` unpushed)** — shipped on `feat/bug-025`
> in 3 units (ec906c8e `modify_dates`, 9aada473 `modify_guests`, docs). **Fix:**
> new `BookingService.reprice_snapshot(quote, *, quotation_line)` mirrors
> `price_line` on the booking side: it keeps the engine figure as `gross`,
> re-applies `quotation_line.discount` as the **same absolute amount, floored
> at 0**, and nets the copy through `_net_snapshot_to_line_total`, so
> `operator_discount`, the netted `total` and `net_to_owner` survive and
> commission/tax clip exactly as at conversion. `modify_dates` and
> `modify_guests` write the netted snapshot and `balance_due` from it, and
> their `BookingEvent` `to_snapshot` records what was written;
> `booking_total_changed` then resizes the schedule to the discounted total.
> **Decision (provisional, 2026-09-17):** option 1, Q-028 #8's suggested
> answer — **Nick has not answered yet**; pro-rata or drop-and-warn is a
> change confined to `reprice_snapshot`. The line's `discount` is
> authoritative: a booking snapshot whose `operator_discount` differs
> (pre-BUG-020 conversion, or a line edited outside the API) is corrected to
> the line on the next reprice. Zero-discount bookings gain `gross` /
> `operator_discount: "0.00"` keys on reprice, no money change.
> **Residuals (unchanged here):** `rental_price` stays the engine
> `rate_subtotal`; a manual-override line's hand-entered price is still
> replaced by the engine figure on reprice (the discount is re-applied on top);
> the FG-018 `total` → `engine_total` rename is still open.

- **Severity:** 🔴 Bug (money — a date or party change on a discounted
  booking quietly puts the operator discount back on the guest's bill).
- **Found:** 2026-09-02, while closing BUG-020. Not yet reproduced by probe;
  read from the code paths below.
- **Blocked on:** a product decision (see "Decision needed").

## Problem

BUG-020 fixed the *conversion* path: `BookingService.create_from_quotation_line`
now books at `line.total` and nets the booking snapshot's `total` /
`net_to_owner` via `_net_snapshot_to_line_total`. The *reprice* paths on the
booking never see the originating line's operator discount:

- `reservations/models/booking.py` — `modify_dates` (~L604-614) and the
  party-change reprice (~L676-683) call the pricing engine and write
  `pricing_snapshot = quote.breakdown`, `balance_due = quote.total`.

Both are raw engine figures, so a booking converted from a line with
`operator_discount = 150.00` comes out of a reprice at the full engine
price. `Booking._resync_payment_schedule()` fires `booking_total_changed`
(`payments/signals.py`) → `PaymentScheduler.resync_for_booking`, which
re-sizes the schedule to the inflated figure, and the GAP-085 `financials`
block follows.

## Decision needed

> 2026-09-16: put to Nick as question 8 of
> [Q-028](../q-028-legacy-loader-owner-questions.md) (suggested answer: option 1).

What should happen to an operator discount when the booking is repriced?

1. **Re-apply the same absolute amount** (`quote.total − operator_discount`,
   floored at 0) — simplest; matches "we agreed £150 off".
2. **Pro-rate it** by the ratio of new engine total to old — keeps a
   percentage-style concession honest across a length change.
3. **Drop it and warn** — the reprice is a new deal; the operator re-enters
   any discount by hand.

Whichever wins, the write should go through the same
`_net_snapshot_to_line_total` helper so `total`/`net_to_owner` stay
consistent with `commission`/`tax` (owner-absorbs, per the BUG-020
decision), and `operator_discount` should be carried onto the new snapshot.

## Tests

- Convert a discounted line, `modify_dates` to a same-length window →
  `balance_due` and `snapshot["total"]` honour the chosen rule.
- Same for the party-change reprice.
- Fully-discounted booking repriced → `net_to_owner` floors at 0.

## Related

- `todo/done/bug-020-quotation-line-discount-lost-on-conversion.md` — the
  conversion half.
- `todo/fg-018-two-keys-named-total.md` — the contract footgun behind both.
- `design/decisions.md` — "Operator discount is netted at conversion".
