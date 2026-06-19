> **✅ RESOLVED (2026-06-19)** — Region `<Select>` added to the property
> listing filter row (country → region → status). Options are slug-valued
> (globally unique via the loader's `-{id}` suffix), mirroring
> `AvailabilityTimelinePage`; the URL `region` param is read into the list
> query and round-trips through the existing `filter_region` (id-or-slug).
> New en+el i18n (`list.filter_region_aria`, `common:filters.any_region`,
> updated `empty_hint`). Reused the existing `filter_region` / `toQuery` /
> `useRegions` plumbing — FE-only, no backend change. Country-scoping of the
> region list deferred (no FE code↔id map, and region already implies
> country). Commit `be5ecde`. Tests (TDD): extended
> `PropertiesListPage.test.tsx` (renders the region filter + forwards region
> to the API); a `/regions` MSW stub keeps the prior 7 tests green; vitest.

# GAP-036 — Region filter on the property listing grid

- **Severity:** Gap (FE-only; backend + region API already shipped).
- **Source:** 2026-06-17 owner Loom (pricing walkthrough, 0:02).
- **Files:**
  - `frontend/src/features/properties/PropertiesListPage.tsx` (filter row;
    country + status selects, no region)
  - `frontend/src/features/properties/api.ts` (`fetchRegions()`),
    `schemas.ts` (`regionSchema`)
  - `django_res/properties/filters/property.py` (`filter_region`, by id or slug)

## Problem

The property listing grid offers **country** and **status** filters but no
**region** dropdown. The owner: "all countries would be nice to have a regional
dropdown here as well, and all the status as well." The status filter he asks
for **already exists**; only region is missing.

The backend already supports it — `PropertyFilter.filter_region` accepts a
numeric region id or a slug — and the frontend already has `fetchRegions()` and
`regionSchema` (used by the availability timeline). `PropertiesListPage.tsx` is
the only place missing the control.

## Proposed fix

Add a **Region** `<select>` to `PropertiesListPage.tsx` alongside the existing
country/status filters, wired to the existing `region` query param via the same
list-query plumbing. Optionally scope region options to the selected country
(regions are children of `Country`). Confirm the existing status filter is
surfaced the way the owner expects (it already exists).

## Acceptance

- Region filter is visible and functional on the listing; selecting a region
  round-trips the `region` query param to the API and narrows results.
- Existing `PropertiesListPage` tests extended to cover the region filter.

## Dependencies

None — backend `filter_region` and the `fetchRegions()` / `regionSchema`
frontend surface already exist. Sibling of the add-property-flow FE cluster.
