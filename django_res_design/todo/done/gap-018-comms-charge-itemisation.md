> **✅ RESOLVED (2026-06-21)** — Charge itemisation is back in guest-facing
> email. A shared `booking_charge_breakdown(booking)` builder
> (`reservations/services/charges.py`) decomposes the billed total into a
> snapshot subtotal + the signed `BookingChargeItem` lines, partitioned by sign
> into `charges` and a separate **Discounts** block (the chosen rendering over
> inline negative lines); its grand total is byte-equal to
> `PaymentScheduler._booking_total`, so the email total always matches what the
> guest is scheduled to pay. The booking-confirmation email and all five
> deposit/balance payment-request emails (`payment.reminder.deposit`,
> `booking.balance_due_today` / `_reminder_3d` / `_reminder_7d`,
> `payment.card_update_request`) render a gated `<mj-raw>` table; the
> security-deposit request is excluded (a separate refundable hold with no
> charge-line decomposition). Reminder querysets prefetch `charge_items` +
> `select_related` the booking currency (no per-row N+1); seed migration
> `comms/0015` re-syncs the changed templates. Commits `7d46be5` (builder),
> `526b5a1` (confirmation), `ae71907` (reminders). Tests (TDD): builder unit +
> scheduler byte-equality + query-free-under-prefetch
> (`reservations/tests/test_charges_breakdown.py`), confirmation render
> (`comms/tests/test_booking_confirmation_itemisation.py`), and per-band reminder
> render + SD-omits + no-charge-gating (`payments/tests/test_payment_reminders.py`).
> **Frontend deferred to [[gap-051-checkout-charge-itemisation]]** — the guest
> checkout SPA page does not exist yet.

# GAP-018 — itemise charge lines in guest-facing comms

- **Severity:** Gap
- **Source:** booking-charge-items work (2026-06-10)
- **Files:** `django_res/comms/` templates, guest checkout SPA surface

## Problem

Legacy showed `VillaBookingDetails` lines itemised on the checkout page and in
booking emails. The rebuild's charge items flow into the payment *amounts*
(the resync resizes the deposit/balance rows, so what the guest is asked to
pay is correct), but nothing guest-facing itemises *why* — a confirmation
email shows a total that no longer decomposes into the lines the guest can
see.

Per the customer-facing parity rule (match ResSystem behaviour for anything
customers/agents see), the itemisation should come back.

## Proposed fix

- Booking confirmation / payment-request email templates: render the charge
  lines (label + signed amount) between the snapshot summary and the total.
- Guest checkout page: same itemisation on the payment summary.
- Decide whether credits render as negative lines (legacy did) or as a
  separate "discounts" block.
