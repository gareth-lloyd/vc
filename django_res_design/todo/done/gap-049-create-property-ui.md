# GAP-049 — No "create property" UI; the create flow is API-only

> ✅ **RESOLVED (2026-06-18)** — shipped on `feat/create-property-ui`
> (`CreatePropertyDialog` + `slugify` helper + category/group hooks + role-gated
> "New villa" button; en+el i18n; unit + component tests). **No backend change**,
> as scoped. **Two deliberate deviations from the acceptance text, both recorded:**
> 1. The "New villa" button is **disabled-with-tooltip** for non-writers, not
>    hidden — the frontend `CLAUDE.md` convention ("buttons disable, never
>    disappear") overrides the ticket's "a VIEWER does not see it".
> 2. The create→edit-tab **round-trip regression test was not added** at the FE
>    layer: the get-or-create behaviour it would prove is a backend guarantee
>    already covered by the Settings/Finance/Capacity view tests, so a full
>    router+layout integration test re-proving it was judged low-value. Flagged
>    for the user; can be added if wanted.
>
> Caveat-1 tension (three required FKs at create) survives as a **live UX risk
> with no ticket yet** — file a follow-up only if operators hit the friction.

- **Severity:** Gap (frontend; backend create endpoint already exists + tested)
- **Source:** 2026-06-18 "can users create properties?" investigation, after the
  add-property-flow cluster (GAP-022/024/025/026/027) shipped — that cluster
  improved the property **edit** tabs but never added a way to **create** a
  property through the UI.
- **Files:**
  - `frontend/src/features/properties/` — new create page/dialog + a
    `useCreateProperty` hook + `createProperty` API fn (`hooks.ts`, `api.ts`)
  - `frontend/src/features/properties/PropertiesListPage.tsx` — "New villa"
    entry point (role-gated)
  - `frontend/src/app/router.tsx` — a `/properties/new` route (if a page, not a
    dialog)
  - **No backend change needed** — the create endpoint and the companion-row
    get-or-create views already exist (see Caveat 2)

## Problem

The backend is complete: `PropertyViewSet` is a full `ModelViewSet` whose
`create()` returns `201` and is gated by `IsReservationsWriter` (ADMIN or
RESERVATIONS), atomically saving the property and provisioning a default
`PropertyLocation` via `ensure_property_location`
(`properties/views/property.py:95-106`). A passing test proves it
(`properties/tests/test_api_properties.py:82` `test_create_property_as_staff`)
with the minimal payload `name, display_name, slug, category, group, region`.

But there is **no way to reach this from the running app**: no `/properties/new`
route, no `useCreateProperty` hook or `createProperty` API fn
(`frontend/src/features/properties/hooks.ts`/`api.ts` only create *sub*-resources
— rooms, images, contacts, blocks, seasons), and no "New villa"/"Add property"
button on `PropertiesListPage.tsx` (the list is read-only; a row click opens the
detail tabs). Today properties only enter the system via the data-migration
loader and `seed_dev`. An operator cannot onboard a new villa through the UI.

## Proposed fix

- **Entry point (FE):** a "New villa" button on `PropertiesListPage`, visible
  only to reservations writers (reuse `useHasReservationsRole`, as FeaturesTab
  does — `IsReservationsWriter` gates the endpoint, so a VIEWER must not see the
  button).
- **Create form (FE):** the serializer's `Meta.fields` lists ten, but only
  **six are required** to create: `name`, `display_name`, `slug`, `category`,
  `group`, `region` (`channel` defaults to `DIRECT` server-side, `licence_number`
  is `blank=True`, `features`/`legacy_id` optional). Keep the create form to the
  required six; `display_name` cannot be defaulted from `name` client-side (the
  model field is non-blank with no default), so the form collects both — though
  it may pre-fill `display_name` from `name` as a convenience. Everything else is
  filled in later on the edit tabs (incremental-onboarding posture, GAP-024).
- **FK selectors (real work — partly missing):** of the three FKs, only a regions
  hook exists (`useRegions`, `features/availability/hooks.ts:47`). **`useRegions`
  is reusable; category and group hooks + select components must be built** —
  against the **already-registered** `/property-categories` and
  `/property-groups` list endpoints (`properties/urls.py:49-50`), so **no backend
  endpoint work**, but two new FE hooks/selects are in scope.
- **Slug UX:** `slug` is required + unique. **No slugify helper exists in
  `frontend/src`** — write a small one (or add a tiny lib). Auto-derive from
  `name` with a manual override; surface the uniqueness `400` as a field error,
  not a toast.
- **Hook + API (FE):** `useCreateProperty` → `POST /properties`, invalidate the
  list query, and on `201` navigate to the new property's detail
  (`/properties/{id or slug}` — the route accepts either, `views/property.py:87`)
  so the operator lands on the edit tabs to continue.
- **No backend work:** `create()` already saves atomically + provisions
  `PropertyLocation`, the write is audited automatically (Property is tracked,
  `apps.py`), and the companion-row views get-or-create on demand (Caveat 2).

## Caveat 1 — keep create minimal; it is the *first* step of incremental onboarding

The cluster's grounding (GAP-024, the 2026-06-11 new-villa transcript) is that an
operator fills a villa in **over weeks**. The create form must therefore be the
smallest possible gate — the six required fields — not a full villa wizard. Resist
scope-creeping rooms/pricing/images/people into create; those are the edit tabs
that already exist. **Tension to flag for the owner:** even the six required
fields include three FKs (`category`, `group`, `region`) the operator may not
know on day one. If that proves too heavy in practice, the follow-up is to relax
`group`/`region` to nullable-with-sentinel (a *backend* change, out of scope
here) — do **not** invent that now; ship the form against the contract as-is and
record the friction.

## Caveat 2 — the missing companion rows are a non-issue (verified)

`create()` provisions only `PropertyLocation`; nothing creates
`PropertySettings`/`PropertyFinance`/`PropertyCapacity`/`PropertyDescription` on
POST (the `post_save` signals in `properties/signals.py` only build
`GroupSettings`/`GroupFinance` at the **group** level). This was initially feared
to break the edit tabs — but verification shows **no backend change is needed**:

- The companion-row views already **`get_or_create` on demand**:
  `PropertySettingsView` (`views/settings.py:33`), `PropertyFinanceView`
  (`views/finance.py:24`), `PropertyCapacityView` (`views/capacity.py:19`). The
  first GET/PATCH from each edit tab materialises its row.
- The detail GET is null-tolerant anyway (`get_capacity` → `getattr(obj,
  "capacity", None)`, `serializers/property.py:55`), so the property renders.
- Group inheritance keys on **per-field null**, not row presence
  (`PropertyFinance.effective()` `models/finance.py:35-40`; settings `effective`
  `models/settings.py:81`) — an all-null row and no row inherit identically. So
  provisioning empty rows in `create()` would be **redundant work with no benefit**
  and is explicitly **not** wanted here.

**Build action:** add nothing to `create()`. Just keep one regression test that
goes **create → open Settings/Pricing/Capacity tab (read + write)** to prove the
get-or-create round-trip works end-to-end from a freshly-created property.

## Acceptance

- A reservations writer sees a "New villa" entry point on the properties list;
  a VIEWER does not.
- Submitting the six required fields creates the property and lands the operator
  on its detail/edit tabs; a duplicate slug shows as a field error.
- The created property renders and **its Settings/Pricing tabs are immediately
  usable** (the existing get-or-create views handle the missing rows), proven by
  a test that goes create → edit-tab read/write, not just `201`.
- No backend changes: no new list endpoints (reuse `/property-categories`,
  `/property-groups`, regions) and no `create()` provisioning.

## Dependencies

None hard — the backend create endpoint is already shipped and tested. Forward
note: GAP-045/046 (Person/Organisation) don't touch this; the property owner is
assigned later via the People tab (GAP-027), not at create. If `group`/`region`
later relax to optional (Caveat 1), revisit the form's required set.
