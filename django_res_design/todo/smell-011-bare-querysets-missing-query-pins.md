# SMELL-011 — Bare `.objects.all()` querysets; `accounts`/`pricing` lack query pins

- **Severity:** 🟡 Smell
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files (re-audited 2026-07-29):** `pricing/views/discount.py:38`,
  `pricing/views/currency.py:19`, `properties/views/geo.py:35,59`,
  `properties/views/metadata.py:13`, `properties/views/collection.py:30`,
  `properties/views/changeover.py:40`, `properties/views/feature.py:16`,
  `reservations/views/terms.py:23,51`, `reservations/views/availability.py:146,301`,
  `accounts/views/user.py:41`
  (note 2026-06-23: `reservations/views/guest.py` is **gone** — the Guest view
  was retired by GAP-045's Person unification. Note 2026-07-29: the original
  headline example `pricing/views/rate.py:211` is **fixed** — all three rate
  viewsets now pin `select_related`/`prefetch_related`, `rate.py:57,171,204`;
  the query-pin-test half of this ticket is unchanged)

## Problem

The CLAUDE.md convention is explicit: "A bare `Model.objects.all()` is a
bug even when the current serializer returns FKs as PKs". ~15 view
querysets violate it, e.g.:

```python
queryset = User.objects.all().order_by("email")  # accounts/views/user.py:41
queryset = Feature.objects.all().select_related("category")  # feature.py:22 — pinned; :16 FeatureCategory is not
```

Many are tiny lookup tables (currency, feature categories) where the cost
is theoretical — the one real list surface among the originals
(`pricing/views/rate.py`) has since been pinned (2026-07-29). Separately,
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
