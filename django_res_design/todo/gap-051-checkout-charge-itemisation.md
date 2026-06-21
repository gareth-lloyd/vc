# GAP-051 — itemise charge lines on the guest checkout page

- **Severity:** Gap (frontend; backend builder already shipped).
- **Source:** GAP-018 split — the email half shipped 2026-06-21; the checkout
  half was deferred because the guest checkout SPA page does not exist yet
  (the router has only staff/owner routes; first-party checkout is future work
  per `django_res_design/workflows/10-payment/checkout-flow.md`).

## Problem

Legacy showed `VillaBookingDetails` lines itemised **both** in booking emails
(done — GAP-018) **and** on the guest checkout page. The checkout-page
itemisation is still missing because the page itself is not yet built.

## Proposed fix (when the checkout page lands)

- Render the same charge breakdown the emails use on the checkout/payment
  summary: a snapshot subtotal line, each positive charge, a separate
  **Discounts** block for credits, and a grand total — matching the email
  layout so the guest sees one consistent decomposition.
- **Reuse the backend, don't re-derive it.** GAP-018 added
  `reservations.services.charges.booking_charge_breakdown(booking)` as the
  single source of truth (snapshot base + signed charge lines, grand total
  byte-equal to `PaymentScheduler._booking_total`). Expose it on whatever
  booking/checkout serializer the checkout page reads, rather than recomputing
  the breakdown in TypeScript.
- Keep the signed-discount contract (the Discounts block) consistent with the
  email rendering.

## Notes

- Depends on the guest checkout page existing — blocked until that surface is
  built.
- See [[gap-018-comms-charge-itemisation]] (done) for the shipped email half
  and the builder contract.
