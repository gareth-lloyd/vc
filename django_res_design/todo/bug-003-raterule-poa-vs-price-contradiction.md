# BUG-003 — `RateRule` lets `is_poa=True` coexist with a numeric price

- **Severity:** 🔴 Bug
- **Source:** the 2026-05-26 data-model deep audit §B3
- **Files:** `pricing/models/rate.py:108–113`

## Problem

`raterule_price_or_poa` enforces only the floor (at-least-one). The
schema accepts `is_poa=True, nightly=500.00` — two contradictory
signals. Pricing-engine output depends on which field the lookup reads
first, which is the textbook silent-divergence bug.

## Proposed fix

Add the mutual-exclusion clause:

```python
CheckConstraint(
    condition=(
        Q(nightly__isnull=False) | Q(weekly__isnull=False) | Q(is_poa=True)
    ) & ~(
        Q(is_poa=True) & (Q(nightly__isnull=False) | Q(weekly__isnull=False))
    ),
    name="raterule_price_xor_poa",
)
```

(Or split into two constraints — one for floor, one for mutex — if the
combined predicate is harder to reason about.)

## Acceptance

- Constraint enforces both rules.
- Test asserts `IntegrityError` on `is_poa=True, nightly=Decimal('50')`.
- Existing pricing tests pass.

## Dependencies

None.

## Resolution

✅ Kept the existing floor constraint `raterule_has_price_or_poa` and added a
separate mutex `raterule_poa_excludes_price`
(`is_poa=False OR (nightly IS NULL AND weekly IS NULL)`) in
`pricing/models/rate.py`; migration `pricing/0007`. Split rather than combined
for readability, as the ticket suggested.

`RateRuleLoader._process_row` now nulls `nightly`/`weekly` when `IsPOA` is set —
POA wins so a legacy "on application" price can never resurface as a concrete
rate. Tests: `test_raterule_poa_cannot_coexist_with_{nightly,weekly}`
(`pricing/tests/test_rate.py`) and `test_transform_poa_drops_price`
(`data_migration/tests/test_rate_rule_loader.py`).
