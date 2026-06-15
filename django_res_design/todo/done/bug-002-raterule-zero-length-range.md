> **✅ RESOLVED (2026-06-15)** — Problem: RateRule allowed zero-length (or inverted) date ranges. Fix: Added a constraint rejecting zero-length RateRule date ranges.
>
> _Original ticket preserved below for context._

# BUG-002 — `RateRule` allows zero-length date ranges

- **Severity:** 🔴 Bug
- **Source:** the 2026-05-26 data-model deep audit §B2
- **Files:** `pricing/models/rate.py:100–103`

## Problem

`raterule_date_from_lte_date_to` uses `__lte`, allowing
`date_from == date_to` — a zero-night rule. `Booking` and `QuotationLine`
use strict `__lt`. The pricing engine's lookup against an empty
`[d, d)` range is either a silent miss or an ambiguous match.

## Proposed fix

Tighten the constraint to match Booking / QuotationLine:

```python
CheckConstraint(
    condition=Q(date_from__lt=F("date_to")),
    name="raterule_date_from_lt_date_to",
)
```

Migration: drop old constraint, add new one. Confirm no existing rows
have `date_from == date_to` before running on staging (one-liner query).

## Acceptance

- Constraint renamed + tightened.
- Test in `pricing/tests/` asserts `IntegrityError` on `date_from == date_to`.
- Pricing-engine tests continue to pass.

## Dependencies

None.

## Resolution

✅ Constraint renamed `raterule_date_from_lte_date_to` → `raterule_date_from_lt_date_to`
(`__lte` → `__lt`) in `pricing/models/rate.py`; migration `pricing/0006`.
`RateRuleLoader._process_row` guard tightened `date_to < date_from` →
`date_to <= date_from` so legacy zero-length ranges skip rather than crash the
new constraint. Regression test `test_raterule_rejects_zero_length_range` in
`pricing/tests/test_rate.py`.
