# GAP-077 — Gross/Net split on deposit & balance schedule components

- **Severity:** 🟢 Gap (booking finance read surface + payment schedule).
  Backend-led.
- **Source:** 2026-07-08 Nick / Gareth res-rebuild call. Nick: "the current
  system doesn't support net, which we need." Wants deposit **and** balance each
  broken into **GROSS** (to client) and **NET** (to owner), with
  **COMMISSION = the difference**, on each component.
- **Files touched (best-guess):**
  - `django_res/reservations/models/booking.py` — `pricing_snapshot` JSON carries
    whole-booking `total` / `commission` / `tax` / `net_to_owner`; `balance_due`
    is a single **gross** figure (~L136); no per-component net.
  - `django_res/properties/models/finance.py` — `PropertyFinance` deposit /
    interim / balance schedule policy + `effective_payment_schedule()`.
  - `PaymentScheduler` — derives deposit/balance amounts from policy.
  - `django_res/reservations/serializers/booking.py` — `get_net_to_owner`
    (whole-booking only).
  - FE booking finance panels.

## Problem

The gross/net/commission split exists only at the **whole-booking** level
(snapshot `total` vs `net_to_owner`). Deposit and balance are derived as single
gross amounts from the schedule policy; there is no `deposit_gross/net`,
`balance_gross/net`, or per-component commission. Owner statements and the sales
team can't see what the owner receives at each payment stage.

## Proposed fix

- When the payment schedule is built, derive per-component **net + commission**
  from the booking's commission rate/policy: for each scheduled component
  (deposit, interim, balance) compute gross (to client), net (to owner),
  commission (difference), consistent with the engine's whole-booking split and
  the non-commissionable carve-out ([GAP-076](gap-076-non-commissionable-extras.md)).
- Surface these on the booking finance read serializer and the owner statement;
  keep the guest-facing schedule as gross.
- Prefer **derive-on-read** from the snapshot + policy over a second stored money
  authority (see SMELL-020).

## Acceptance

- Booking finance shows, for deposit and balance each: gross, net-to-owner,
  commission — summing to the whole-booking figures. (serializer test)
- Non-commissionable extras (GAP-076) land in the correct component's gross
  without inflating its commission. (test)
- Quality gate green.

## Dependencies

- Depends on **GAP-076** (commissionable flag feeds each component's commission
  base).
- Related **SMELL-020** (single money authority — derive, don't add a parallel
  store), **GAP-035** (net/gross derivation, done), **Q-006 / Q-015** (owner
  statements / visibility, done).
