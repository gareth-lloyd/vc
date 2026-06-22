# BUG-009 — Pricing engine ignores `RatePlan.price_basis` (GROSS plans mis-priced)

> 🟨 **SPEC SLICE DONE (2026-06-22).** The corrected, `price_basis`-aware engine
> maths are now specified: `04-pricing.md` Services steps 8-9 (GROSS carve-out /
> NET gross-up, mode-dependent tax/commission bases, fixed-vs-percentage
> commission, exemption), the authoritative-field note (`RatePlan.price_basis`
> vs `PropertySettings.prices_entered_as`), a Deferred row in `10-decisions.md`,
> and an expanded `TODO(finance-rewrite)` + assembly pointer in
> `pricing/services/engine.py`. **Engine code remains deferred to the finance
> rewrite** — the `_call_finance_resolver` shim must be removed first. The
> single-source-of-truth reconciliation with `prices_entered_as` is tracked in
> GAP-035. Ticket stays open until the engine branch lands.

- **Severity:** 🔴 Bug (wrong money out) — **fix deferred to the finance rewrite;
  corrected spec lands now.**
- **Source:** 2026-06-02 pricing audit; legacy `RatesModel.Calculate()`
  (`RatesModel.cs:114-254`). User chose "spec + todo only" (2026-06-02).
- **Files:**
  - `django_res/pricing/services/engine.py` (`_compute_commission` 345-369,
    `_compute_tax` 372-395, `_call_finance_resolver` shim 327-343)
  - `django_res/pricing/models/rate.py` (`price_basis` 25-29)
  - `django_res/data_migration/loaders/properties.py:258` (hardcodes every plan to `GROSS`)
  - design: `04-pricing.md` (engine "Steps" 8-9, ~lines 308-310)

## Problem

`RatePlan.price_basis` (GROSS/NET) exists, is in the admin + API, and is set on
every imported plan to **GROSS** (`loaders/properties.py:258`) — but the engine
**never reads it**. `_compute_commission`/`_compute_tax` always do `base × pct/100`
and **add** the result to the total (`engine.py:175-188`).

Legacy `Calculate()` is mode-dependent:
- **GROSS** (customer-facing, tax/commission *inclusive*): carve out —
  `tax = gross × rate/100`, `commission = (gross − tax) × pct/100`,
  `net = gross − tax − commission`. The guest total **is** the rate.
- **NET** (owner net): gross up — `commission = net/(1 − pct/100) − net`,
  `tax = (net + commission)/(1 − rate/100) − (net + commission)`,
  `gross = net + commission + tax`.

So for a GROSS plan (all of them today) the engine **adds** tax+commission on top
of a price that already includes them → the guest is over-charged and
`net_to_owner` is wrong. It only doesn't bite yet because finance is a near-stub
returning zeros in tests.

## Proposed fix

**Now (spec):** rewrite `04-pricing.md` engine steps 8-9 to be `price_basis`-aware
— document the GROSS carve-out and NET gross-up exactly as legacy
`RatesModel.Calculate()`, noting fixed-vs-percentage commission and that the tax
base differs by mode. Expand the `TODO(finance-rewrite)` comment at
`engine.py:336-339` to reference BUG-009. Add a row to `10-decisions.md`
"Deferred" table.

**Later (code, with the finance rewrite):** branch `_compute_commission`/
`_compute_tax` (and the `total`/`net_to_owner` assembly) on
`RatePlan.price_basis` per the corrected spec.

## Acceptance

- `04-pricing.md` steps 8-9 describe both modes; no "always add" wording remains.
- `10-decisions.md` deferred row points here.
- (Deferred) engine tests assert GROSS carve-out and NET gross-up against
  legacy-derived numbers; `net_to_owner` correct for a GROSS plan with non-zero
  tax + commission.

## Dependencies

- **Blocked on the finance rewrite** — the `_call_finance_resolver` shim
  (`engine.py:327-343`) exists because `PropertyFinance.effective_*` still returns
  no-arg dicts. The mode-aware fix lands when that shim is removed.
- Relates to [FG-001](fg-001-booking-quotation-currency-drift.md) (also pricing-snapshot money correctness).
- Note: `PropertyFinance` does **not** model NET/GROSS — basis lives on
  `RatePlan`; the finance side only needs to supply pct / fixed / exempt (it
  already does), so no new finance field is required.
