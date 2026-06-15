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

## Resolution (2026-06-15)

Option 1 implemented. Added a single-purpose helper
`pricing.services.currency.quantise_money(amount, currency)` that rounds to
`currency.decimal_places` (ROUND_HALF_EVEN, matching the hand-rolled
`.quantize(Decimal("0.01"))` calls it replaces). Invoked at the
service-layer persistence points where a money field is written alongside a
known currency:

- `reservations/services/quotations.py` — `QuotationService.price_line`
  (`QuotationLine.total`, against the line's resolved currency).
- `payments/services/refund.py` — `RefundService.request` (`Refund.amount`).
- `payments/services/manual_payment.py` — `ManualPaymentService.record`
  (`Payment.amount`).
- `payments/services/security_deposit.py` —
  `SecurityDepositService.create_for_booking` (`SecurityDeposit.amount`) and
  the BT mark-paid `Payment` write.
- `payments/services/payment_scheduler.py` — DEPOSIT/BALANCE `Payment.amount`
  on both `create_for_booking` and `resync_for_booking`.
- `pricing/services/currency.py` — `FxConverter.convert` now quantises to the
  target currency rather than a hard-coded 2 dp.

No DB constraint and no data migration: the live portfolio is all 2-dp
currencies (EUR/GBP/USD), so existing rows already satisfy their precision;
write-time validation is sufficient and avoids any risk of rewriting historic
money. Option 2 (integer minor units) remains on the table if zero-decimal
currencies (JPY) become real.

Tests: `pricing/tests/test_quantise_money.py` (helper, incl. 0/2/3-dp and
half-even rounding) and a JPY end-to-end case in
`payments/tests/test_refund.py`. Full gate green
(pytest 1721 passed, ruff, ruff format, mypy, lint-imports).
