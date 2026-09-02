# BUG-019 — Property feature filtering does not work: no `features` filter exists anywhere, and the `/features` endpoint ignores `?category=` + truncates at 50 rows

- **Severity:** 🔴 Bug
- **Source:** 2026-07-08 GTD capture ("Property feature filtering does not
  work"), investigated + filed 2026-07-29
- **Files:** `properties/filters/property.py:16–64` (`PropertyFilter`, no
  feature param), `properties/views/feature.py:21–24` (`FeatureViewSet` — no
  `filterset_class`, no `pagination_class`),
  `properties/models/features.py:75–79` (`PropertyFeature.is_derived`),
  `villacollective/settings/base.py:159–168` (global `PAGE_SIZE: 50`),
  `frontend/src/features/properties/schemas.ts:366–376` +
  `api.ts:86–97` (no features field), `frontend/src/features/admin/tags/api.ts:23–28`
  + `TagsAdminPage.tsx:218,227–228,323–336,361–363` (sends the ignored
  `category` param; hardcodes `pageCount={1} pageSize={100}`),
  `frontend/src/features/properties/tabs/FeaturesTab.tsx:62,104` (page-1-only
  `featuresById`)

## Problem

"Filter properties by feature" (pool, sea view, aircon, …) does not work
because **it was never built end-to-end**, and the one feature-filter UI that
*does* exist is silently broken:

1. **No property feature filter, backend.** `PropertyFilter`
   (`filters/property.py:16–64`) declares `status / category / region /
   country / collection / min_bedrooms / max_bedrooms / min_guests / q /
   changeover_day / date_from / date_to / include_unavailable` — nothing
   feature-shaped. `Property.features` (M2M through `PropertyFeature`,
   `models/property.py:60–65`) is simply never exposed as a filter.

2. **No property feature filter, frontend.** `PropertyFilters`
   (`schemas.ts:366–376`) and `toQuery()` (`api.ts:86–97`) carry nothing
   feature-related; `PropertiesListPage` has country/region/status selects +
   search only; the quote-builder candidate search
   (`quotations/api.ts:139–190`) likewise — even though the designed enquiry
   brief includes a feature chip multi-select
   (`design/product/03-workflows.md:56,100`) and legacy pricing accepted
   `FeatureIds` (`legacy/workflows/04-pricing/pricing-engine.md:13`).

3. **Live bug — `/features?category=` is silently ignored.** The Tags admin
   category `<Select>` (`TagsAdminPage.tsx:218`) refetches via
   `featureQuery()` (`tags/api.ts:23–28`) with a `category` param, but
   `FeatureViewSet` (`views/feature.py:21–24`) declares **no filterset**, so
   `DjangoFilterBackend` is a no-op — picking a category returns the
   identical unfiltered list. This is the "filtering does not work" an
   operator can actually observe today.

4. **Live bug — `/features` truncates at 50 rows.** No `pagination_class` →
   global `PAGE_SIZE: 50` with no `page_size` param honoured. The FE assumes
   the list is complete: `TagsAdminPage.tsx:361–363` renders `pageCount={1}
   pageSize={100}`; `FeaturesTab.tsx:104` / `DetailsTab.tsx:33` build
   `featuresById` from page 1 only. GAP-067 documents a ~300-row
   `VillaFeatures` catalogue, so features 51+ are invisible in the add-picker
   and any already-assigned one renders as `features.row.unknown_feature`
   (`FeaturesTab.tsx:62`).

## Why it's a bug (not just a gap)

Items 3–4 are wrong **today**: the Tags admin ships a filter control that
does nothing, and three screens silently truncate/mislabel data at 50 rows.
Items 1–2 are the missing surface the capture actually asked for — filed
here rather than as a GAP because the product spec already promises it
(feature chips in the enquiry brief, legacy `FeatureIds`) and users read the
absence as breakage.

## Traps for the fix (from investigation)

- **`category` name collision — cleared 2026-09-02.** `PropertyFilter.category`
  *was* taken by `PropertyCategory` (`filters/property.py:25`); GAP-093 removed
  `Property.category` and that filter, so the name is free for a
  feature-category filter on `/properties`.
- **`.distinct()` or inflated counts.** The features M2M join multiplies
  rows; the existing multi-valued filters call `.distinct()`
  (`filters/property.py:79–80`). A features filter that forgets it inflates
  the paginator `COUNT` and duplicates rows.
- **Derived-features backfill dependency (GAP-067).** Derived links live on
  the same join table (`PropertyFeature.is_derived`), so `features__slug`
  filtering matches manual + derived alike — but only after
  `recompute_derived_features` has run. On a dataset without that backfill a
  "pool" filter returns zero properties even though rooms carry the
  attribute. Cutover runbook must include the recompute.
- **Convention violation while in there.** `PropertyViewSet` redeclares
  `filter_backends` (`views/property.py:70–71`), which the project convention
  bans (filterset_class ONLY) and which drops the default `SearchFilter` for
  that viewset. Same pattern at `accounts/views/organisation.py:36`,
  `accounts/views/user.py:42`, `accounts/views/contact.py:155`,
  `reservations/views/client.py:52`.

## Proposed fix

1. `FeatureViewSet`: add a small filterset (`category`, maybe `q`) + the
   opt-in `ConfigurablePageSizePagination` (as geo/collections/rooms already
   use); FE tags admin passes a real `page_size`/pagination instead of
   `pageCount={1}`, and `FeaturesTab`/`DetailsTab` fetch the full catalogue.
2. `PropertyFilter`: add a multi-value `features` filter (slug- or id-based;
   decide AND vs OR semantics — legacy `FeatureIds` was AND) with
   `.distinct()`; mirror in `PropertyFilters`/`toQuery()` and add the feature
   chip multi-select to the property list and (per the spec) the
   quote-builder candidate search.
3. Sweep the redundant `filter_backends` declarations while touching the
   viewsets.

## Acceptance

- `/api/v1/features?category=X` returns only that category; a test hits the
  endpoint with a query (today nothing in `django_res/` does).
- All ~300 features reachable from the Tags admin, FeaturesTab add-picker,
  and `featuresById` (no `unknown_feature` rows for real assignments).
- `/api/v1/properties?features=…` filters correctly for manual **and**
  derived links, with a stable paginator count (`.distinct()` covered by
  test).
- FE property list (and quote-builder search, if included in scope) sends the
  param and round-trips it through the URL like the existing filters.

## Dependencies

GAP-067 (taxonomy cleanup — filtering over a dirty ~300-row catalogue with
5× aircon duplicates will frustrate; either land first or accept interim);
GAP-082 (villa Zoho payload also reads features). Tests: backend has zero
feature-filter coverage; FE `TagsAdminPage.test.tsx:78–81` stubs `/features`
ignoring the query string, so bug 3 is invisible to the suite — fix the stub
to assert the param.
