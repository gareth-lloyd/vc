# GAP-077 — Gross/Net split on deposit & balance schedule components

> **✅ RESOLVED (2026-07-10)** — shipped on `feat/gap-077` in 6 units
> (`d3e850a`, `9a2463c`, `4da33aa`, `98272b0`, `54b043b`, + docs).
> - **Derive-on-read** (SMELL-020, no second money store):
>   `payment_component_splits(booking)` in
>   `reservations/services/owner_finance.py` allocates the whole-booking
>   owner money (snapshot + GAP-076 `charges_owner_adjustments` overlay,
>   all figures 2dp-quantized at the boundary) across the DEPOSIT/BALANCE
>   schedule components **pro-rata by scheduled gross**, residual cent to
>   BALANCE (the scheduler's own convention); pure N-component
>   `allocate_proportionally` means a future INTERIM slots in with zero
>   rework. Tax is surfaced per component alongside commission so rows sum
>   (gross − net = commission + tax on GROSS villas).
> - Component gross/status/due_at mirror `TrackSerializer` semantics via
>   string literals (spine: reservations < payments), set-equality-pinned
>   in `payments/tests/test_component_splits_parity.py` against the new
>   `TERMINAL_NON_ACTIVE_STATUSES` constant; both sides tie-break
>   latest-row on `(created_at, pk)`. Σ-gross drift (partial mark-paid,
>   manual rows, resync residual) keeps Σ commission/tax exact and per-row
>   identities; the FE caveats Σ-net drift.
> - **Exposure:** staff `BookingDetailSerializer.payment_splits` (+
>   `get_net_to_owner` consolidated onto `owner_money_for_booking`,
>   payments prefetch on the detail path); owner API **detail-only** inside
>   the `view_full_money`-gated block (list keeps its 12-query pin); shared
>   `format_component_split` wire shape. Guest surfaces never split.
> - **FE:** FinanceTab "Payment schedule split" table (totals row, waived
>   badge, drift caveat, UTC-day due dates) + owner-portal "Payment
>   schedule" cards ("Your share" vocabulary; loose purpose schema so an
>   additive backend purpose degrades instead of killing the page); en+el.
> - GAP-079's worked example extended per-component: deposit 3,000 →
>   522/390/2,088; balance 7,000 → 1,218/910/4,872 (sums 1,740/1,300/6,960).
> - Deliberately pinned: INTERIM stays rolled into BALANCE (deferred,
>   user-confirmed); per-transaction (capture/refund-level) splits out of
>   scope; the `quotations.py` operator-discount snapshot-clobber is
>   pre-existing and untouched (splits read final snapshot figures only).

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
