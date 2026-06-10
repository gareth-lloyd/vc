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
