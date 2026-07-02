> **❌ DROPPED (2026-06-15)** — Problem: effective() was reported to crash when property.group is null. Fix: Dropped: Property.group is non-nullable, so the null case cannot occur.
>
> _Original ticket preserved below for context._

# FG-003 — `effective()` crashes if `property.group` is null

- **Status:** ❌ **DROPPED** (2026-05-27 critique) — premise is false.
  `Property.group` is non-nullable with `on_delete=PROTECT` and no
  `null=True`. The "null group" case is schema-impossible. The
  group.settings/group.finance 1:1-missing variant is a migration-window
  detail already handled by data_migration sentinels.
- **Severity:** 🟠 Footgun
- **Source:** the 2026-05-26 data-model deep audit §F3
- **Files:** `properties/models/finance.py:39`,
  `properties/models/settings.py:88`

## Problem

```python
return getattr(self.property.group.settings, attr)
```

If `Property.group_id` is nullable and ever `NULL`, this resolver raises
`AttributeError`. Same hazard for `group.settings` / `group.finance` 1:1
rows that don't exist yet (mid-migration window).

## Proposed fix

Choose one:

1. **Make `Property.group` non-nullable.** Migrate orphans to a `Default`
   sentinel group (similar to the `unknown_country` pattern in
   `data_migration/loaders/sentinels.py`). Adds a hard floor.
2. **Hard-coded defaults in `effective()`.** If `self.property.group_id
   is None`, return the per-field default (`""`, `0`, `None`,…). Cheaper
   but spreads default-knowledge across the resolver.

Recommendation: option 1 if we can sentinel-default in data migration;
option 2 if not.

## Acceptance

- `effective()` does not raise on a property with no group / no
  group.settings / no group.finance — either because those cases are
  schema-impossible, or because the resolver returns a sensible default.
- Test covering both shapes.

## Dependencies

May fold into [FG-002](../fg-002-effective-null-vs-empty-string.md) since
both touch the same resolver — consider doing them together.
