# GAP-079 — Commission-after-local-VAT: confirm ordering + per-villa policy

> **✅ RESOLVED (2026-07-09)** — verify-only close: the ordering Nick described
> is the engine's existing GROSS branch (`tax = base×rate`, then
> `commission = (base−tax)×pct`), verified against legacy
> `RatesModel.Calculate()` (tax L201, commission on the post-tax remainder
> L223-228); NET (commission gross-up, then tax on net+commission) is legacy
> parity too. **No per-villa "commission after tax" toggle added** — legacy has
> none; ordering is a function of `price_basis` alone (decision row:
> `design/decisions.md`). A **constructed** worked example (13% VAT / 20%
> commission / 10,000 gross → tax 1,300, commission 1,740, owner net 6,960;
> deposit 3,000 / balance 7,000 off the snapshot total) is pinned in
> `pricing/tests/test_engine_price_basis.py` (GAP-079 section) and
> `payments/tests/test_payment_scheduler.py`, and documented in
> `design/backend/04-pricing.md` — **re-reconcile against a real villa
> statement when Nick provides one** (no real numbers existed at close).
> The non-taxable-extras interaction is deferred to GAP-076 via a coordination
> note in that ticket.

- **Severity:** 🟢 Gap (mostly **verify-and-extend** — the engine largely already
  does this). Backend.
- **Source:** 2026-07-08 Nick / Gareth res-rebuild call. Nick: some villas take
  local VAT (e.g. 13%) off the gross **first**, then commission off the
  remainder; "treat it like a mandatory extra / tax, same principle."
- **Files touched (best-guess):**
  - `django_res/pricing/services/engine.py` — `_derive_commission_and_tax`
    (~L784-840). The **GROSS** branch already does
    `tax = base × rate/100; commission = (base − tax) × pct/100` — i.e. VAT off
    gross, then commission off the remainder. The **NET** branch grosses up
    commission then tax.
  - `django_res/properties/models/finance.py` —
    `PropertyFinance.tax_percentage` / `tax_is_exempt`, `effective_tax_policy()`.

## Problem

The "commission after VAT" ordering the client wants is **already implemented**
for the GROSS basis, but: (a) it isn't obviously configurable per villa as a
distinct "commission after VAT" policy; (b) the NET-basis ordering may not match
some villas' expectation; and (c) VAT currently applies to the entire base
including all extras, with no interaction yet with non-commissionable extras
([GAP-076](gap-076-non-commissionable-extras.md)). This is a verify-and-extend,
**not** a rebuild.

## Proposed fix

- Confirm with **worked examples** (a real villa's numbers from Nick) that the
  GROSS branch matches the villa's "13% VAT then commission" expectation;
  document it in `design/`.
- Decide whether a per-villa "commission after tax" toggle is actually needed, or
  whether `price_basis` + `tax_percentage` already covers it — add the toggle
  **only** if a villa's real behaviour diverges.
- Coordinate with GAP-076 so non-commissionable extras can also be flagged
  non-taxable where a villa treats them that way.

## Acceptance

- A worked example from a real villa reconciles against the engine for **both**
  deposit and balance. (engine test with the villa's numbers)
- Any per-villa policy divergence found is captured as explicit config, not
  hardcoded.
- Quality gate green.

## Dependencies

- Tightly coupled to **GAP-076** (non-commissionable base) and **GAP-077**
  (per-component net).
- Related **BUG-009** (price_basis engine, done), **SMELL-021** (price_basis two
  sources).
