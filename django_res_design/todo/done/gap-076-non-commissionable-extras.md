# GAP-076 — Non-commissionable charges: `commissionable` flag on extras (+ charge items)

> **✅ RESOLVED (2026-07-10)** — shipped on `feat/gap-076` in 5 units
> (`3c6932a`, `ebf7399`, `eaac29c`, `4df5b67`, `2578c89`).
> - `Extra.commissionable` + `BookingChargeItem.commissionable`
>   (`BooleanField(default=True)`, migrations `pricing/0004` +
>   `reservations/0004`, serializers, filterset, audit `track()` lists).
> - **Engine split** (`pricing/services/engine.py`): the commission base is
>   `rate_subtotal + commissionable extras − discounts`; non-commissionable
>   extras bill the guest verbatim, ride on top of `total` in both GROSS and
>   NET branches, and pass through to the owner untouched. **Full
>   pass-through semantics** (user decision): excluded from the commission
>   **and** tax bases, and never discounted (percent discounts compute on the
>   commissionable subtotal only). Snapshot gains explicit `commission_base`
>   (basis-dependent — read with `price_basis`) + `extras_non_commissionable_total`
>   keys and per-extra `commissionable` flags; `Quote` mirrors them as typed
>   fields for GAP-077.
> - **Charge items**: `charges_owner_adjustments` (services/charges.py) is the
>   single shared owner-side arithmetic — only commissionable lines enter the
>   `owner_effect` percent skim; non-commissionable lines (and credits,
>   symmetric) flow to the owner in full. Staff `get_net_to_owner`, owner
>   booking serializer and owner-dashboard YTD all ride it; guest-facing
>   totals/schedules never split. `with_charges_total` annotates the
>   non-commissionable slice via a second SELECT-only Subquery (no new
>   queries on list paths).
> - **FE**: "Commissionable" checkbox (default ticked) in the rate-workbench
>   Extra dialog + booking ChargeItem dialog; "Non-commissionable" tags in
>   the extras list, price-probe result card and FinanceTab charge rows;
>   en+el locales.
> - Deliberately pinned: over-discount beyond the commissionable subtotal
>   erodes the pass-through extra, keeping the guest total identical to
>   pre-GAP-076 (`test_over_discount_erodes_pass_through_extra_not_guest_total`).
> - Per-villa/per-extra **taxability** toggle NOT added (GAP-079 coordination
>   closed: full pass-through, no toggle); the quotations operator-discount
>   snapshot-clobber (`quotations.py`) is pre-existing and recorded for
>   GAP-077.

- **Severity:** 🟢 Gap (pricing/finance model + engine). Backend-led, FE
  follow-through. **Nick's top near-term finance ask.**
- **Source:** 2026-07-08 Nick / Gareth res-rebuild call. Two real cases:
  (a) a compulsory **chef cost** is non-commissionable and must **reduce the
  commission base** (the owner's sneaky commission haircut — "20 grand villa,
  chef's a grand, commission on the nine[teen] grand"); (b) a **pool-heating**
  add-on is non-commissionable but still added to the guest **balance/total**.
  Nick also framed mandatory local VAT as "a mandatory extra, same principle"
  (see [GAP-079](done/gap-079-commission-after-local-vat.md)).
- **Files touched (best-guess):**
  - `django_res/pricing/models/extra.py` — `Extra` has
    `kind/calc/amount/is_mandatory/…` but **no `commissionable` field**.
  - `django_res/pricing/services/engine.py` — `PricingEngine.quote` folds every
    extra into a single `base` (~L284) that is then fully commissionable **and**
    taxable in `_derive_commission_and_tax` (~L784-840).
  - `django_res/reservations/models/charge_item.py` +
    `django_res/reservations/services/charges.py` — `owner_effect` (~L157-175)
    treats every manual charge as commissionable-base (percent) or owner-only
    (fixed), globally, not per-line.
  - `frontend/src/lib/pricing/netGross.ts` (display mirror), extras admin UI,
    rate-workbench extras editor.

## Problem

Every extra and every manual charge item is implicitly fully commissionable.
There is no way to (a) keep a mandatory extra in the guest total while excluding
it from the commission base, nor (b) exclude a manual add-on from commission.
This blocks accurate owner economics for a large slice of real villas.

## Proposed fix

1. Add `commissionable: bool` (default `True`) to `Extra` and to
   `BookingChargeItem` (migration + serializers + workbench / extras editors).
2. Split the engine's commission base: `commissionable_base = rate_subtotal +
   commissionable extras − discounts`. Non-commissionable extras stay in the
   guest total/balance but are excluded from the commission (and, per villa
   policy, possibly from tax — confirm under GAP-079). Keep the GROSS/NET
   branches (BUG-009) intact; only the base composition changes.
3. Update `owner_effect` / owner-finance to honour per-line `commissionable`
   flags instead of the global percent/fixed heuristic.
4. FE: expose the flag in the extras / charge editors and reflect it in net/gross
   display (`netGross.ts`) and owner economics.

## Acceptance

- A mandatory non-commissionable extra appears in the guest total but does not
  increase commission; owner net rises accordingly — tested on **both** GROSS and
  NET basis. (engine test)
- A non-commissionable manual charge item is excluded from commission but still
  bills the guest. (test)
- Extras without the flag set default to all-commissionable — existing behaviour
  unchanged. (regression test)
- Quality gate green.

## Dependencies

- Interacts with **GAP-079** (commission-after-VAT — decide whether
  non-commissionable extras are also non-taxable, per villa).
  > **GAP-079 coordination note (2026-07-09).** GAP-079 closed as
  > verify-only: the VAT-then-commission ordering is the existing GROSS
  > branch (legacy parity, no per-villa toggle — see
  > `design/decisions.md`). What it leaves for THIS ticket: when adding
  > `commissionable` to `Extra`/`BookingChargeItem`, settle taxability in
  > the same unit — either a parallel `taxable` flag or an explicit
  > "non-commissionable ⇒ still taxable" default — because today the
  > entire base (all extras) feeds the VAT base
  > (`04-pricing.md` step 8 note; pinned by
  > `test_gross_extras_and_discount_fold_into_base`). Don't ship the
  > commission carve-out with taxability left implicit.
- Feeds **GAP-077** (per-component deposit/balance net split reads the same
  commission base).
- Builds on **BUG-009** (price_basis engine, done) and **GAP-035** (net↔gross
  derivation, done).
- Related **SMELL-020** (booking money authority) / **SMELL-021** (price_basis
  two sources) — keep the single-authority direction.
