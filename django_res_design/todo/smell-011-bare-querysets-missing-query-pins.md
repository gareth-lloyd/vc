# SMELL-011 — Bare `.objects.all()` querysets; `accounts`/`pricing` lack query pins

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `pricing/views/rate.py:211`, `pricing/views/discount.py:29`,
  `pricing/views/currency.py:19`, `properties/views/geo.py:34,53`,
  `properties/views/metadata.py:16,22`, `properties/views/collection.py:26`,
  `properties/views/changeover.py:40`, `properties/views/feature.py:16`,
  `reservations/views/terms.py:23,51`, `reservations/views/availability.py:142`,
  `reservations/views/guest.py:61`, `accounts/views/user.py:40`

## Problem

The CLAUDE.md convention is explicit: "A bare `Model.objects.all()` is a
bug even when the current serializer returns FKs as PKs". ~15 view
querysets violate it, e.g.:

```python
queryset = RateRule.objects.all()          # pricing/views/rate.py:211
queryset = Guest.objects.all()             # reservations/views/guest.py:61
queryset = User.objects.all().order_by("email")  # accounts/views/user.py:40
```

Many are tiny lookup tables (currency, feature categories) where the cost
is theoretical — but `guest.py:61` and `rate.py:211` sit on real list
surfaces. Separately, the convention requires an `assert_max_queries` pin
on at least one list endpoint per app: `accounts/` and `pricing/` test
suites have none (every other app has at least one).

## Proposed fix

- Add the `select_related`/`prefetch_related` each serializer actually
  walks (for pure-scalar lookup tables a brief comment that the queryset is
  deliberately flat is acceptable — make it a decision, not an accident).
- Add one `assert_max_queries` list-endpoint regression test each to
  `accounts/tests/` and `pricing/tests/`.

## Acceptance

- No undocumented bare `.objects.all()` in viewset/list-view querysets.
- Query-count pins exist for an accounts and a pricing list endpoint.

## Dependencies

None.
