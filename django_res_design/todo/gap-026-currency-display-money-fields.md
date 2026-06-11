# GAP-026 — Show the property currency beside every money field

- **Severity:** Gap (UX / data-quality guard)
- **Source:** 2026-06-11 new-villa setup transcript review; product decision
  recorded 2026-06-11
- **Files:** `frontend/src/features/properties/tabs/SettingsTab.tsx`
  (finance section), `RateRuleFormDialog.tsx`, `SeasonDetailPanel.tsx`,
  `properties/models/settings.py` (`PropertySettings.currency`),
  `properties/models/finance.py`

## Problem

Legacy has no currency anywhere on the finance/payment-schedule fields
(`VillaFinance` has type enums only; `CurrencyId` lives on rates). The
loader flagged it on the security deposit specifically: "there actually
isn't a currency here… we do have some villas that quote in pounds."
The new model has the same shape — `PropertyFinance` amounts are bare
decimals; currency lives on `PropertySettings.currency` — so the operator
entering "2000" security deposit has no confirmation of what currency
they're committing to.

## Decision (recorded)

**Do not mix currencies within a property.** `PropertySettings.currency`
(group-inherited) is the single source of truth for all of a property's
money fields — finance amounts, rate prices, extras. No per-field currency
is added. (Mixed currencies *across* properties in the quote builder
remain expected and are not in scope — see GAP-014.)

## Proposed fix

- Display the effective property currency (code/symbol, resolved through
  group inheritance) as an adornment on every fixed-amount money input in
  the Finance section (deposit, interim, security deposit, cancellation)
  and on rate price inputs.
- Where the property currency is unset at group and property level, show
  a prompt linking to the settings field rather than a blank.
- Backend check: confirm rate plans/cards can't be created in a currency
  different from the property's; if they can, add validation (or a
  follow-up ticket) so the no-mixing decision is enforced, not just
  displayed.

## Acceptance

- Finance and rate forms show the resolved currency next to amounts.
- Decision recorded in `10-decisions.md` (single currency per property).
- Validation (or explicit follow-up ticket) covering rate-plan currency
  vs property currency.

## Dependencies

Touches the same surfaces as GAP-019 (`security_deposit_calculate_from`).
