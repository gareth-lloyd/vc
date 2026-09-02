# GAP-093 — Remove `Property.category`: country + region is enough

> **✅ RESOLVED (2026-09-02, local `main` unpushed)** — shipped on `feat/gap-093`
> in 3 units (backend removal, frontend removal, docs). **Problem:** the
> Create-a-villa dialog demanded a Category before it would create a villa;
> Nick (2026-07-20 recording): country + region is enough. `Property.category`
> was a non-nullable PROTECT FK carrying a full `/property-categories`
> ModelViewSet, an admin registration, a legacy loader + reconcile check, a
> factory SubFactory, and an embedded object in the Zoho villa push — nothing
> read it for behaviour. **Fix:** migration `properties/0006` (`RemoveField` +
> `DeleteModel`, one-way in practice — restore from backup to reverse); the
> model, three staff serializers + the owner-portal serializer, the
> `?category=` filter, both `select_related("category")` sites, the audit
> field, the endpoint/views/serializers/admin, the `PropertyCategoryLoader` +
> `VillaPropertyCategory` reconcile check, and the factory all deleted
> (31 backend test modules swept). Frontend: category dropped from
> `CreatePropertyDialog`, schemas (create form is now four fields), hooks,
> query keys, both locales, and the owner-portal schema (the GAP-070 M3 trap —
> it was a required `z.number().nullable()`). Docs: `COVERAGE.md` Dropped table
> (+ stale `VillaGroup` rows fixed), `CUTOVER.md`, design backend/product docs.
> **Zoho contract:** the villa payload's `category` key is dropped outright
> (amendment recorded in `done/gap-082-zoho-villa-push.md`); ⚠️ **Limitless
> must be told** at the next touchpoint. **Deploy note:** Render migrates
> pre-deploy, so old code 500s on `select_related("category")` for the swap
> window — expected blip. **Unblocks BUG-019** (`PropertyFilter.category` name
> is free for feature-category filtering).

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
  - **A whole CRUD API surface, easy to miss:**
    `django_res/properties/urls.py:50` registers `/property-categories` as a
    full **`ModelViewSet`** (`views/metadata.py`, `serializers/metadata.py` —
    both modules exist only for this model), plus the `__init__.py` exports in
    `properties/{models,serializers,views}/`.
  - `django_res/properties/admin.py:17, 36` — registered in Django admin.
  - `django_res/properties/factories.py:195` (`PropertyCategoryFactory`) and
    `:236` (`PropertyFactory.category = SubFactory(...)`). **This is why the
    test blast radius is smaller than the file count suggests** — most suites
    inherit the category through the factory and need no edit; deleting the
    `SubFactory` line covers them.
  - `django_res/data_migration/loaders/lookups.py` — where
    `PropertyCategoryLoader` is actually *defined*;
    `data_migration/registry.py:29, 64` only registers it.
  - `django_res/data_migration/management/commands/reconcile_legacy.py:103` —
    a `SELECT COUNT(*) FROM VillaPropertyCategory` check that must be removed
    with the loader, not left to fail.
  - `django_res/data_migration/loaders/sentinels.py:4` — its docstring cites
    the in-line "Uncategorised" `PropertyCategory` fallback as the pattern it
    mirrors; reword rather than orphan the reference.
    Also `data_migration/COVERAGE.md` and `seeding/README.md`.
  - **25 test modules** reference `PropertyCategory` — mostly conftests and
    the loader tests (`data_migration/tests/conftest.py:29`,
    `test_property_loader.py:15`, `test_quotation_loader.py:124`,
    `test_rate_band_loader.py:21`, `properties/tests/*`, `comms/tests/*`, …),
    plus `reservations/management/commands/demo_ical.py`.
  - `frontend/src/features/properties/components/CreatePropertyDialog.tsx` —
    default `category: 0` (L45), controller (L57), options fetch (L110),
    `<Select>` (L180–198).
  - `frontend/src/features/properties/api.ts:384` — the `/property-categories`
    fetch backing that options list; goes with the endpoint.
  - `frontend/src/features/properties/schemas.ts` — **two** call sites: the
    read shape (`:56`, already `.nullable().optional()`) and the create form's
    `z.number().int().min(1)` (`:432`), which is what makes the field
    mandatory in the UI.
  - `__tests__/CreatePropertyDialog.test.tsx`,
    `frontend/src/i18n/locales/en/properties.json:24, 25, 39`
    (`category`, `category_placeholder`, `category_required`) — and the `el`
    locale alongside it.

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

1. Drop the field from the create dialog and the property serializers, and
   the `/property-categories` fetch that feeds the dropdown.
2. Retire the `/property-categories` endpoint — router registration, viewset,
   serializer, `__init__` exports, admin registration, factory.
3. Drop `Property.category` and the `PropertyCategory` model; retire
   `PropertyCategoryLoader` (definition in `loaders/lookups.py`, registration
   in `registry.py`) and its `reconcile_legacy` check.
4. Drop the `?category=` filter from `PropertyFilter` — **and take the name
   with it**: BUG-019 needs `PropertyFilter.category` for feature-category
   filtering and is currently blocked by this collision (its own "traps"
   section names it). Landing this first removes the obstacle.
5. Strip the now-pointless `PropertyCategory` fixtures — start with the
   `PropertyFactory.category` `SubFactory`, which clears most of them at once.
6. Record the deliberate drop of the legacy `VillaPropertyCategory` table in
   `CUTOVER.md` and `COVERAGE.md`.

## Acceptance

- A villa can be created with name / display name / slug / country / region
  only. (component test)
- `PropertyCategory` and the FK are gone; migrations apply cleanly and the
  pending-migrations guard test passes.
- `?category=` no longer resolves to property category on `/properties`.
- `/api/v1/property-categories` is gone (404), and no frontend query still
  requests it. (test)
- `reconcile_legacy` runs clean with the `VillaPropertyCategory` check
  removed; the deliberate drop is documented, not an unexplained gap.
- Quality gate green (backend + frontend).

## Dependencies

- **Unblocks BUG-019** — frees `PropertyFilter.category` for the feature
  filter. Land this first, or resolve the naming inside BUG-019.
- Precedent: **GAP-070** (remove property groups) — same shape of removal,
  same screen; reuse its approach.
