# SMELL-023 — Two money-rounding conventions coexist; hardcoded 2dp paths mis-round for 0/3-decimal currencies

- **Severity:** 🟡 Smell (dormant until a non-2dp currency goes live)
- **Source:** the 2026-07-02 backend complexity audit (rounding scattered vs centralized)
- **Files:** `payments/services/security_deposit.py:582–583` (`_size_sd`) +
  `:95` (double-quantise via `quantise_money`),
  `payments/services/payment_scheduler.py:260,273,275`,
  `payments/services/refund.py:422,424`,
  `payments/services/security_deposit.py:424` (`claim()` capture — unquantised),
  `pricing/services/currency.py` (`quantise_money`, currency-aware),
  `payments/models/currency.py` (`Currency.decimal_places`)

## Problem

Money is consistently `Decimal` (no float leakage — checked), but there are
**two rounding conventions**:

- `quantise_money()` is currency-aware — it respects `Currency.decimal_places`
  (BHD = 3dp, JPY = 0dp), per SMELL-003's resolution.
- Four hot paths bypass it and hardcode `.quantize(Decimal("0.01"))`:
  `_size_sd` (`security_deposit.py:582–583`), the payment scheduler
  (`payment_scheduler.py:260,273,275`), and the refund cancellation-fee /
  refundable math (`refund.py:422,424`).

Two secondary snags fall out of the same seam: in `create_for_booking` the SD
amount is rounded to 2dp by `_size_sd` and then **re-quantised** by
`quantise_money` (`security_deposit.py:95`) — double rounding, and for a 3dp
currency the first step already truncated the third place; and `claim()`
writes the operator-supplied `captured_amount` into `Payment.amount`
(`security_deposit.py:424`) **without** `quantise_money` at all (the only
Payment-minting path that skips it).

## Why it bites

The day a 0- or 3-decimal currency (JPY / BHD) is enabled, SD sizing and
cancellation refunds silently mis-round while payment mints round correctly —
producing reconciliation drift that is painful to trace back to "one service
hardcoded `0.01`." It's invisible today because every live currency is 2dp.

## Proposed fix

Delete the hardcoded `.quantize(Decimal("0.01"))` calls and funnel all money
rounding through `quantise_money(value, currency)`. Remove the double-quantise
in `create_for_booking` (round once). Quantise `captured_amount` in `claim()`
before it reaches `Payment.amount`.

## Acceptance

- No `.quantize(Decimal("0.01"))` literals remain in `payments/services/`;
  every money round goes through `quantise_money`.
- Test: an SD sized in a 3dp currency and a cancellation refund in a 0dp
  currency round to the currency's places (not 2dp), and `claim()` rejects/
  rounds an over-precise `captured_amount`.

## Dependencies

Extends SMELL-003 (`Currency.decimal_places` made authoritative). Independent
of Q-024. Touches the same `claim()`/capture path GAP-054 will revisit.
