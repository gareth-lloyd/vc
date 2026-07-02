# BUG-009 — Pricing engine ignores `RatePlan.price_basis` (GROSS plans mis-priced)

> **✅ RESOLVED (2026-07-02)** — The engine branch landed, **independently of
> the finance rewrite** (superseding the 🟨 banner below): the mode-aware maths
> only need pct / fixed / exempt, which already flow through the
> `_call_finance_resolver` shim, so the shim (and its dict/attr tolerance)
> simply **stays** until the real rewrite. Shipped:
> `PricingEngine._derive_commission_and_tax` branches on the resolved plan's
> `price_basis` per `04-pricing.md` steps 8-9 — GROSS carve-out
> (`tax = base×rate/100`; `commission = (base−tax)×pct/100`; `total = base`) /
> NET gross-up (`commission = base/(1−pct/100)−base`;
> `tax = (base+raw_comm)/(1−rate/100)−(base+raw_comm)`;
> `total = base+comm+tax`), with the **raw** commission feeding the NET tax
> base (quantize each component to 0.01 at the end — matches the GAP-035
> `netGross.ts` hint), fixed commission flat in both modes (divergence closed),
> and ≥100%/zero-base sanitisation guards (documented legacy divergence).
> Breakdown snapshots `price_basis` + `net_to_owner`; the FE probe workaround
> is **unwound** (probe trusts the engine `total`, owner economics rendered).
> Commits: `fd3df63` (engine, TDD `test_engine_price_basis.py`), `0e80f0d`
> (quotation + bulk-endpoint regression pins), `cd5a2e5` (FE unwind), plus the
> spec close-out (`04-pricing.md` steps 8-10 flipped to implemented,
> `10-decisions.md` Deferred row → ✅ BUILT).

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

- **Severity:** 🔴 Bug (wrong money out) — corrected spec landed 2026-06-22;
  **engine fix landed 2026-07-02** (the "deferred to the finance rewrite" plan
  was superseded — see Dependencies).
- **FE workaround (2026-07-01, unwound 2026-07-02):** the Rate & Service Workbench price probe
  no longer renders the mis-priced engine `total` as the guest figure. For GROSS
  plans it shows `rate_subtotal + extras − discount`; for NET plans the engine
  `total` plus a reconciling "Taxes & fees" line. Basis from the winning plan's
  `price_basis` → `PropertySettings.prices_entered_as` → `"gross"`. See
  `frontend/src/features/rate-workbench/components/QuoteResultCard.tsx` +
  `PriceProbePanel.tsx`. **Revisited and unwound (2026-07-02, commit
  `cd5a2e5`):** with the engine branch landed the recompute is gone — the
  probe trusts the engine `total` again and renders owner economics.
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

**Later (code — landed 2026-07-02, independently of the finance rewrite):**
branch the commission/tax derivation (and the `total`/`net_to_owner` assembly)
on `RatePlan.price_basis` per the corrected spec — shipped as
`_derive_commission_and_tax` + `_resolve_commission_policy` /
`_resolve_tax_policy` (the old `_compute_commission`/`_compute_tax` are gone).

## Acceptance

- `04-pricing.md` steps 8-9 describe both modes; no "always add" wording remains.
- `10-decisions.md` deferred row points here.
- ~~(Deferred)~~ ✅ (2026-07-02) engine tests assert GROSS carve-out and NET
  gross-up against legacy-derived numbers, and `net_to_owner` is correct for a
  GROSS plan with non-zero tax + commission —
  `pricing/tests/test_engine_price_basis.py` (14 tests, incl. quantization
  order, guards, projection), plus consumer pins in
  `reservations/tests/test_quotation_service.py` and
  `pricing/tests/test_api_pricing.py`.

## Dependencies

- ~~**Blocked on the finance rewrite**~~ — **superseded (2026-07-02, user
  call):** the mode-aware maths only need pct / fixed / exempt, which already
  flow through the `_call_finance_resolver` shim, so the engine branch landed
  independently of the finance rewrite. The shim (and its dict/attr tolerance)
  **stays** until the real rewrite — see `TODO(finance-rewrite)` in
  `engine.py` (`_resolve_commission_policy` / `_resolve_tax_policy` are the
  seams to simplify).
- Relates to [FG-001](fg-001-booking-quotation-currency-drift.md) (also pricing-snapshot money correctness).
- Note: `PropertyFinance` does **not** model NET/GROSS — basis lives on
  `RatePlan`; the finance side only needs to supply pct / fixed / exempt (it
  already does), so no new finance field is required.
