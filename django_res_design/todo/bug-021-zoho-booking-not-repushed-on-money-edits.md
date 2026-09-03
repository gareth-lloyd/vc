# BUG-021 — Zoho booking record goes stale after charge-item and payment-row edits

- **Severity:** 🔴 Bug (integration — Zoho shows money figures and payment
  state that res has since changed; sharpened by GAP-099, which put
  `deposit_status` / `balance_status` into the same block).
- **Found:** 2026-09-02, by the `/ship gap-099` code review (verifier
  confirmed by reading `reservations/signals.py` + `payments/signals.py`;
  **not reproduced by test yet — write the failing test first**).

## Problem

The booking payload (`build_booking_payload`) embeds `financials` (GAP-085,
GAP-099) and `extras[]`, both derived from `BookingChargeItem` rows and
`Payment` rows. But the re-push only fires on a `Booking` post_save (the
`auto_push` receiver in `integrations/signals.py`) or a LEAD `BookingGuest`
save (`reservations/signals.py:~215`). Writes that change the money without
touching the booking row:

- `BookingChargeItem` create / edit / delete → `_charge_item_changed`
  (`reservations/signals.py:~159`) only sends `booking_total_changed`, whose
  receiver rewrites `Payment` / `SecurityDeposit` / `BookingEvent` rows and
  never calls `Booking.save()` or `enqueue_zoho_push(booking)`.
- `PaymentScheduler.resync_for_booking` resizing PENDING rows, a deposit
  override set/clear (GAP-087), a waive, a manual mark-paid that does **not**
  transition the booking status.

For a CONFIRMED booking there may be no later status transition at all, so
Zoho keeps the pre-edit `total_gross` / `net_balance`, an `extras[]` missing
the new line, and (post GAP-099) a `deposit_status` that no longer matches
FinanceTab — until someone runs `zoho_backfill --kind booking`.

## Fix sketch

Enqueue a booking re-push from the same seams that already know the money
moved: the `booking_total_changed` receiver (charge items + resync) and the
`Payment` post_save for status changes on schedule rows. Reuse the existing
dispatch dedupe (GAP-081 amendment 2) so a charge-item burst is one push.
Guard with `push_suppressed()` / `webhook_url("booking")` like the sibling
receivers. Test: add a charge item to a CONFIRMED booking → exactly one
booking push enqueued; mark the deposit paid → one push.

## Related

- **BUG-022/023 (resolved 2026-09-03)** changed what a stale push can mean:
  `deposit_status` now reads `"cancelled"` on a **live** booking whose deposit
  was cancelled because none is wanted, so a booking that never re-pushes can
  sit in Zoho showing a deposit state that no longer exists in either
  direction. Tell Limitless to read `deposit_status == "succeeded"` for
  "paid?", never `"cancelled"` for "booking dead?".

## Out of scope

- Zoho-side insert-only behaviour (CHECK-004 item 1) — until Limitless fix
  that, the re-push lands as a duplicate; still correct on our side.
