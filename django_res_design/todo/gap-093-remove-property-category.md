# GAP-093 — Remove `Property.category`: country + region is enough

- **Severity:** 🟢 Gap (dead concept — required field with no purpose).
  Backend + frontend. Unblocks a BUG-019 name collision.
- **Source:** 2026-07-20 Nick screen-recording (`Recording-20260720_134424`,
  reviewed 2026-08-11). Transcript `[00:43–01:05]`; our Create-a-villa dialog
  captured at `[00:50]`.
- **Files touched (verified):**
  - `django_res/properties/models/property.py:50` — `category` FK to
    `PropertyCategory`, **non-nullable, `on_delete=PROTECT`** (so it is
    required on every create today), plus the `PropertyCategory` model itself.
  - `django_res/properties/serializers/property.py:103, 165, 226` — three
    serializers.
  - `django_res/properties/filters/property.py:25, 52` — `?category=` query
    param (`NumberFilter(field_name="category_id")`).
  - `django_res/data_migration/registry.py:29, 64` — `PropertyCategoryLoader`.
  - ~10 test modules construct a `PropertyCategory` purely to satisfy the
    non-null FK (`data_migration/tests/conftest.py:29`,
    `test_property_loader.py:15`, `test_quotation_loader.py:124`,
    `test_rate_band_loader.py:21`, …).
  - `frontend/src/features/properties/components/CreatePropertyDialog.tsx` —
    default `category: 0` (L45), controller (L57), options fetch (L110),
    `<Select>` (L180–198).
  - `frontend/src/features/properties/schemas.ts`,
    `__tests__/CreatePropertyDialog.test.tsx`,
    `frontend/src/i18n/locales/en/properties.json`.

## Problem

The Create-a-villa dialog asks for a **Category** before it will create the
villa. Nick `[00:43]`: *"create villa — we can remove category. We don't need
category; country and region is enough there."*

The legacy General panel carries it alongside `Group` (visible at `[01:45]`,
set to `NotSet` on the example villa) — the same vintage of dead lookup that
`Group` was, and `Group` is already gone our side (GAP-070). Nothing
downstream reads it for behaviour: it is a lookup FK, a filter param no UI
sends, and a loader that populates it.

It is not merely unused — because the FK is non-nullable it forces a required
field on the create form and a fixture in every test that builds a Property.

## Proposed fix

1. Drop the field from the create dialog and the property serializers.
2. Drop `Property.category` and the `PropertyCategory` model; retire
   `PropertyCategoryLoader` from the registry.
3. Drop the `?category=` filter from `PropertyFilter` — **and take the name
   with it**: BUG-019 needs `PropertyFilter.category` for feature-category
   filtering and is currently blocked by this collision (its own "traps"
   section names it). Landing this first removes the obstacle.
4. Strip the now-pointless `PropertyCategory` fixtures from the test modules
   that only create one to satisfy the FK.
5. Check `reconcile_legacy` for a `PropertyCategory` row count and record the
   deliberate drop in `CUTOVER.md`.

## Acceptance

- A villa can be created with name / display name / slug / country / region
  only. (component test)
- `PropertyCategory` and the FK are gone; migrations apply cleanly and the
  pending-migrations guard test passes.
- `?category=` no longer resolves to property category on `/properties`.
- `reconcile_legacy` gap for the dropped table is documented, not
  unexplained.
- Quality gate green (backend + frontend).

## Dependencies

- **Unblocks BUG-019** — frees `PropertyFilter.category` for the feature
  filter. Land this first, or resolve the naming inside BUG-019.
- Precedent: **GAP-070** (remove property groups) — same shape of removal,
  same screen; reuse its approach.
