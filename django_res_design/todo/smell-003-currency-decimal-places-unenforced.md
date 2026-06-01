# SMELL-003 — `Currency.decimal_places` is informational, not enforced

- **Severity:** 🟡 Smell
- **Source:** the 2026-05-26 data-model deep audit §S3
- **Files:** `pricing/models/currency.py`, money-bearing fields on
  `Payment`, `RateRule`, `QuotationLine`, etc.

## Problem

`Currency.decimal_places` is stored per currency, but money fields are
all `DecimalField(max_digits=12, decimal_places=2)`. A JPY value of
`100.00` fits the field but violates the currency's own metadata. No
code path coerces on save.

## Proposed fix

Two options:

1. **Quantise on save.** Service-layer write paths call
   `amount.quantize(Decimal(10) ** -currency.decimal_places)` before
   persisting. Cheap, single-purpose helper in `pricing.services`.
2. **Store integer minor units.** "Always work in pence" — store
   amounts as `BigInteger`, derive display from `Currency.decimal_places`.
   More invasive; better long-term hygiene.

Recommendation: option 1 in the short term, with option 2 on the table
for a future refactor if zero-decimal currencies become real (JPY for
Asia portfolio, etc.).

## Dependencies

None for option 1.
