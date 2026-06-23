# SMELL-011 — Bare `.objects.all()` querysets; `accounts`/`pricing` lack query pins

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `pricing/views/rate.py:211`, `pricing/views/discount.py:29`,
  `pricing/views/currency.py:19`, `properties/views/geo.py:34,53`,
  `properties/views/metadata.py:16,22`, `properties/views/collection.py:26`,
  `properties/views/changeover.py:40`, `properties/views/feature.py:16`,
  `reservations/views/terms.py:23,51`, `reservations/views/availability.py:142`,
  `accounts/views/user.py:40`
  (note 2026-06-23: `reservations/views/guest.py` is **gone** — the Guest view
  was retired by GAP-045's Person unification; re-audit the surviving list views)

## Problem

The CLAUDE.md convention is explicit: "A bare `Model.objects.all()` is a
bug even when the current serializer returns FKs as PKs". ~15 view
querysets violate it, e.g.:

```python
queryset = RateRule.objects.all()          # pricing/views/rate.py:211
queryset = User.objects.all().order_by("email")  # accounts/views/user.py:40
```

Many are tiny lookup tables (currency, feature categories) where the cost
is theoretical — but `rate.py:211` sits on a real list surface. Separately,
the convention requires an `assert_max_queries` pin on at least one **list
endpoint** per app: `accounts/` still has none, and `pricing/`'s only pin
(`pricing/tests/test_engine.py:982`) covers the **engine quote path**, not a
list endpoint — so neither app satisfies the convention yet. Don't mis-read
the pricing pin as resolving this.

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
