# BUG-002 — `RateRule` allows zero-length date ranges

- **Severity:** 🔴 Bug
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` §B2
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
