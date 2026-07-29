# SMELL-023 — Two money-rounding conventions coexist; hardcoded 2dp paths mis-round for 0/3-decimal currencies

- **Severity:** 🟡 Smell (dormant until a non-2dp currency goes live)
- **Source:** the 2026-07-02 backend complexity audit (rounding scattered vs centralized)
- **Files:** `payments/services/security_deposit.py:579–580` (`_size_sd`) +
  `:96` (double-quantise via `quantise_money`),
  `payments/services/payment_scheduler.py:252,254`,
  `payments/services/refund.py:456,458`,
  `pricing/services/currency.py` (`quantise_money`, currency-aware),
  `payments/models/currency.py` (`Currency.decimal_places`)

> **2026-07-29 refresh:** line refs above updated to the current tree, and the
> original "`claim()` capture — unquantised" sub-claim is **struck** — the
> SD capture / mark-paid Payment mints now pass through
> `quantise_money(amount, sd.currency)` (`security_deposit.py:317`). The
> surviving hardcoded-2dp paths are `_size_sd`, the scheduler percent maths,
> the refund fee/refundable maths, and the `_size_sd`→`quantise_money`
> double-round.

## Problem

Money is consistently `Decimal` (no float leakage — checked), but there are
**two rounding conventions**:

- `quantise_money()` is currency-aware — it respects `Currency.decimal_places`
  (BHD = 3dp, JPY = 0dp), per SMELL-003's resolution.
- Three hot paths bypass it and hardcode `.quantize(Decimal("0.01"))`:
  `_size_sd` (`security_deposit.py:579–580`), the payment scheduler
  (`payment_scheduler.py:252,254`), and the refund cancellation-fee /
  refundable math (`refund.py:456,458`).

A secondary snag falls out of the same seam: in `create_for_booking` the SD
amount is rounded to 2dp by `_size_sd` and then **re-quantised** by
`quantise_money` (`security_deposit.py:96`) — double rounding, and for a 3dp
currency the first step already truncated the third place. *(The original
fourth path — `claim()` writing an unquantised `captured_amount` — was fixed;
see the 2026-07-29 note above.)*

## Why it bites

The day a 0- or 3-decimal currency (JPY / BHD) is enabled, SD sizing and
cancellation refunds silently mis-round while payment mints round correctly —
producing reconciliation drift that is painful to trace back to "one service
hardcoded `0.01`." It's invisible today because every live currency is 2dp.

## Proposed fix

Delete the hardcoded `.quantize(Decimal("0.01"))` calls and funnel all money
rounding through `quantise_money(value, currency)`. Remove the double-quantise
in `create_for_booking` (round once). *(`claim()` already quantises —
2026-07-29.)*

## Acceptance

- No `.quantize(Decimal("0.01"))` literals remain in `payments/services/`;
  every money round goes through `quantise_money`.
- Test: an SD sized in a 3dp currency and a cancellation refund in a 0dp
  currency round to the currency's places (not 2dp).

## Dependencies

Extends SMELL-003 (`Currency.decimal_places` made authoritative). Independent
of Q-024. Touches the same `claim()`/capture path GAP-054 will revisit.
