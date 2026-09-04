# BUG-026 — A booking that wants no deposit is parked in `awaiting_deposit` forever

- **Severity:** 🔴 Bug (money workflow — the booking never advances, and a
  balance that settles is swallowed as an invalid transition).
- **Found:** 2026-09-03, while fixing BUG-022/023 (`/ship bug-022-023`
  planning + adversarial review). Pre-existing; **not** introduced by that fix,
  which only adds one more route into the state.

## Problem

Nothing advances a booking out of `AWAITING_DEPOSIT` except `payment_succeeded`
/ `payment_waived` on a **DEPOSIT** row:

- `payments/signals.py` `_advance_booking_on_payment_settled` (`:112-147`)
  dispatches DEPOSIT → `Booking.record_deposit`, BALANCE → `Booking.record_balance`,
  and swallows `InvalidTransition` with a warning.
- `reservations/models/booking.py` `record_deposit` (`:429-437`) is the only
  `AWAITING_DEPOSIT → DEPOSIT_PAID` edge; `record_balance` (`:448-459`) admits
  `DEPOSIT_PAID` / `AWAITING_BALANCE` only.
- `reservations/tasks.py` `expire_bookings` (`:119-145`) only expires bookings
  that hold a PENDING deposit row, so the stranded booking never expires either.

A booking with **no deposit row** therefore sits in `AWAITING_DEPOSIT` until an
operator intervenes. When the guest pays the balance, `record_balance` raises,
the receiver logs `payment.booking_advance_skipped`, and the money is recorded
against a booking that still reads as unpaid.

## Reachable via

1. `PropertyFinance.deposit_required=False` at confirmation —
   `PaymentScheduler.create_for_booking` creates no deposit row (`:110`).
2. A zero `deposit_override_amount` present at confirmation (pinned by
   `test_create_for_booking__zero_override_creates_no_deposit_row`).
3. **New since BUG-022 (2026-09-03):** a zero override (or a policy flip to
   `deposit_required=False`) on resync cancels the PENDING deposit row.
4. **Also new since BUG-022:** *over-collection* — committed money already
   covers the total, so the deposit target is 0 and the row is cancelled with
   kind `DEPOSIT_COVERED` even though a deposit is still nominally wanted. A
   booking whose BALANCE settled while it was still `AWAITING_DEPOSIT` (that
   advance is itself swallowed, see above) loses its deposit row on the next
   resync and strands with a 0.00 PENDING balance beside it. Whichever fix is
   chosen must cover this route too, not just the "no deposit wanted" ones.

## Fix sketch

Either:

- **Advance on schedule.** When the scheduler leaves a booking with no
  active DEPOSIT row while it is `AWAITING_DEPOSIT` (create or resync), move it
  to `DEPOSIT_PAID` via a dedicated `Booking.skip_deposit()` transition that
  writes a `BookingEvent` (reason `deposit_not_required`) — the balance then
  flows through `arm_balances` / `record_balance` as normal. Cleanest for
  Zoho (`deposit_status` reads as `"cancelled"` / absent, booking status
  honest) and for the reminder/expiry sweeps; or
- **Widen `record_balance`.** Let `record_balance` admit `AWAITING_DEPOSIT`
  when no ACTIVE deposit row exists, jumping straight to `BALANCE_PAID`.
  Smaller change, but the booking still reads `awaiting_deposit` until the
  balance lands, and expiry stays undefined for it.

Prefer the first. Either way, `expire_bookings` needs a rule for no-deposit
bookings (probably: none — there is nothing unpaid to wait for).

Tests to write first: `deposit_required=False` confirmation → booking status;
zero override on resync → booking status; balance settle on each → `BALANCE_PAID`
with no `payment.booking_advance_skipped` warning.

## Related

- `todo/done/bug-022-…` / `todo/done/bug-023-…` — the resync cancel that adds
  route 3.
- `todo/done/gap-087-…` — the zero-override-at-creation gate.
- `todo/bug-021-…` — Zoho is not re-pushed on schedule changes, so the
  stranded state also goes stale in Zoho.
