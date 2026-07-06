# GAP-051 — itemise charge lines on the guest checkout page

> **⛔ STILL BLOCKED (re-confirmed 2026-07-06)** — a `/ship gap-051` attempt
> re-verified against the code that the prerequisite guest checkout surface
> does not exist, so this ticket cannot be built as scoped:
> - **No guest route.** Every frontend route sits behind `RequireAuth` →
>   `RequireStaff`/`RequireOwner` (`frontend/src/app/router.tsx:100-636`). The
>   only "payment" screens are staff/owner admin (`PaymentsTab`,
>   `/bookings/:id/payments`). No public/guest checkout route or component.
> - **No backing field.** The design
>   (`django_res_design/legacy/workflows/10-payment/checkout-flow.md`) calls for
>   a first-party SPA driven by `Booking.checkout_url`; that field does not
>   exist (`grep checkout_url django_res` → nothing), and there is no guest
>   checkout endpoint.
> - **Service ready, unexposed.** `booking_charge_breakdown(booking)`
>   (`django_res/reservations/services/charges.py:95`) is the layout contract
>   (subtotal + signed charge lines + Discounts block + grand total, byte-equal
>   to the scheduler, matching the GAP-018 confirmation email), but it is **not**
>   on any DRF serializer — only email contexts (`comms/contexts.py:35`) and
>   `payments/tasks.py:396` consume it. Once a checkout serializer exists it will
>   need a new `charge_breakdown` read field wired to this service.
>
> **Do not start this ticket until the guest checkout page + its serializer
> exist.** Exposing `charge_breakdown` on the staff booking serializer early was
> considered and rejected as a currently-unconsumed field (KISS/YAGNI).

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
