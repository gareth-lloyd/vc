# GAP-009 — Discount loose ends (REPEAT_GUEST dead, `uses_count` inert, `DiscountApply` dropped)

- **Severity:** 🟢 Gap / 🟠 footgun (mixed) — **document + light clean-up now;
  REPEAT_GUEST + `uses_count` wiring deferred.**
- **Source:** 2026-06-02 pricing audit. User chose "document + clean up" (2026-06-02).
- **Files:**
  - `django_res/pricing/services/engine.py` (`_apply_discounts` 279-325 — REPEAT_GUEST skip 314-315, `uses_count` cap check 300)
  - `django_res/pricing/services/discounts.py` (`apply_discount` 9-19)
  - `django_res/pricing/models/discount.py`, `django_res/pricing/enums.py` (`RuleKind`)
  - design: `04-pricing.md` (step 7), `09-departures.md` (Pricing table)

## Problem

Three loose ends, plus a framing correction:

1. **`REPEAT_GUEST` is a dead enum.** `_apply_discounts` silently `continue`s on
   it (`engine.py:314-315`); no repeat-guest detection exists anywhere. But
   `04-pricing.md` step 7 lists it as an auto-apply kind — so the spec promises a
   behaviour the engine silently no-ops.
2. **`uses_count` is never incremented.** The engine reads it for the `max_uses`
   cap (`engine.py:300`) and the serializer marks it read-only, but no booking
   path writes it → **`max_uses` is currently unenforceable** (a promo with
   `max_uses=1` can be redeemed unlimited times). There is also no cap preventing
   total discount > subtotal.
3. **`DiscountApply` (legacy gross/net application target) has no rewrite home.**
   `apply_discount` applies to whatever subtotal it's handed, basis-blind.
4. **Framing:** legacy rate-level discount fields
   (`IsDiscount`/`DiscountRate`/`DiscountType`/`DiscountApply`/`DiscountNight`)
   were stored but **never applied** in the legacy quote engine
   (`RatesModel.Calculate()` reads `DiscountType` into an enum and stops). So the
   rewrite's `Discount` engine is **net-new**, not a reproduction — there is no
   legacy behaviour being lost, only legacy *intent* being realised for the first time.

## Proposed fix

**Now (code + docs):**
- `_apply_discounts`: make REPEAT_GUEST an **explicit** exclusion (filter at the
  queryset with a comment "recognised but unimplemented in v1"), so it can never
  silently mis-apply. Keep the enum member (avoid migration / API churn).
- `04-pricing.md` step 7: drop REPEAT_GUEST from the auto-apply list; add a
  one-line "not implemented in v1" note.
- `09-departures.md` Pricing table: add a row — legacy rate-discount fields →
  `pricing.Discount`, disposition **Added/Replaced**, rationale "legacy stored but
  never applied these; rebuild makes discounts first-class and actually applied;
  `DiscountApply` gross/net target intentionally dropped."

**Deferred (separate slice, booking layer):**
- Wire `uses_count` increment + `max_uses` enforcement into the booking-creation
  path (`reservations` / `BookingService.create_from_quotation_line`) when promo
  redemption is built. Decide whether to add a discount-total cap (≤ subtotal).
- Repeat-guest detection (needs guest history) if/when REPEAT_GUEST is wanted.

## Acceptance

- A `REPEAT_GUEST` discount is provably never applied (test asserts it doesn't
  reduce the total) and is excluded explicitly, not by silent `continue`.
- `04-pricing.md` step 7 no longer promises REPEAT_GUEST auto-apply.
- `09-departures.md` records the discount disposition + `DiscountApply` drop.
- A follow-up note (here) tracks the deferred `uses_count`/`max_uses` wiring.

## Resolution

✅ Now-slice shipped (code + docs).
- `_apply_discounts` (`engine.py`): `REPEAT_GUEST` is now excluded at the
  queryset (`.exclude(rule_kind=RuleKind.REPEAT_GUEST)`) with a comment marking
  it "recognised but unimplemented in v1"; the dead inner `continue` was removed.
  It can no longer silently mis-apply.
- Test `test_repeat_guest_discount_never_applied` in `pricing/tests/test_engine.py`
  proves a would-otherwise-match REPEAT_GUEST discount never reduces the total.
- `04-pricing.md` step 7 drops REPEAT_GUEST from the auto-apply list and adds the
  "not implemented in v1" note.
- `09-departures.md` Pricing table: the Discount row now records the Added/Replaced
  disposition (legacy stored-but-never-applied), the `repeat_guest` v1 exclusion,
  the deferred `uses_count`/`max_uses` wiring, and the intentional `DiscountApply` drop.

**Deferred (still open, booking-redemption slice):** `uses_count` increment +
`max_uses` enforcement on the booking-creation path; the discount-total ≤ subtotal
cap; repeat-guest detection if/when REPEAT_GUEST is wanted.

## Dependencies

- `uses_count`/`max_uses` enforcement depends on the booking-creation slice.
- Discount math itself is correct today (`apply_discount`); this ticket is about
  the unbuilt/inert edges, not the core path.
