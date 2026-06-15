# GAP-026 — Show the property currency beside every money field

- **Severity:** Gap (UX / data-quality guard)
- **Source:** 2026-06-11 new-villa setup transcript review; product decision
  recorded 2026-06-11; 2026-06-11 email thread — customer confirmed they want
  "currency shown clearly against deposits and prices"
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

**Multi-currency *per* property is intentional and load-bearing (see
GAP-014).** A `RatePlan` carries its own required currency;
`resolve_property_currency()` (`pricing/services/currency.py`) derives a
property's currency *from* its plans; `pick_preferred_plan()` breaks
same-day mixed-currency ties; the pricing engine quotes in any currency;
~18 legacy mixed-currency overlaps exist. `PropertySettings.currency` is a
tie-break / display *hint*, **not** an enforced single source of truth.
Therefore **no** backend "no-mixing" constraint will be added. (Mixed
currencies *across* properties in the quote builder remain expected and are
not in scope — see GAP-014.)

**Villa Groups stay in the rebuild.** The group-inheritance currency
resolution depends on them. The owner's suggestion to remove groups was
assessed as premature (it reasoned from the legacy system, where groups
were unused) — do not design around their removal.

## Proposed fix

FE adornment only — no backend changes.

- For rate / season inputs, source the currency from the `RatePlan`'s own
  `currency_code` (the serializer already exposes it), **not** the settings
  chain. Display it as an adornment on every rate price input.
- For fixed-amount finance inputs (deposit, interim, security deposit,
  cancellation), use `PropertySettings.effective('currency')` resolved
  through *group* inheritance, displayed as an adornment. Both property- and
  group-level currency are nullable, so handle a `None` result by prompting
  to set the currency rather than showing a blank.
- Add an optional, **non-blocking** soft warning when a rate plan's currency
  differs from the property's effective currency — a flag, not a wall.

## Acceptance

- Finance and rate forms show the resolved currency next to amounts (rate
  inputs from the rate plan's `currency_code`; finance inputs from the
  group-inherited effective currency, with a set-currency prompt on `None`).
- A non-blocking soft warning appears when a rate plan's currency differs
  from the property's effective currency.
- Decision recorded in `10-decisions.md` (multi-currency per property is
  intentional; `PropertySettings.currency` is a display hint, not enforced).

## Dependencies

Touches the same surfaces as GAP-019 (`security_deposit_calculate_from`).
