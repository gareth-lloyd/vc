# GAP-060 — retire the legacy property "Pricing" tab; rename the Workbench to "Rates"

- **Severity:** Gap (two property-admin tabs now edit the same rate model; the
  older one is a strict subset of the newer, so it's dead weight that confuses
  staff and doubles the maintenance surface for every rate change)
- **Source:** stub `gap-060`; supersession established when the Rate & Service
  Workbench shipped ([[project_rate_workbench]]) alongside — not instead of —
  the original `PricingTab`. Rate model is period-native post-GAP-056
  ([[project_gap056_rate_restructure]]) and renamed `RateRule`→`RateBand`
  (SMELL-019).
- **Blocks:** nothing hard. But until this lands there are **two** admin tabs
  ("Pricing" and "Rate Workbench") editing the same `Property → RatePlan →
  RatePeriod → RateBand` tree through partly-different affordances — staff have
  to know which tab does what, and any rate-UI change has to be made (or
  consciously skipped) in both.
- **Blocked by:** the parity work in Unit 1 below **must land before** the old
  tab is deleted (Unit 3), or we degrade modeling capability. Also see the soft
  dependency on [GAP-059](gap-059-rate-period-name-compulsory.md) under
  *Dependencies*.
- **Frontend-only.** No backend, no migration, no API change — every endpoint
  the parity work needs already exists and is already used by `PricingTab`.

## Files

The old tab (to remove — see Unit 3 for exactly what's safe):
- `frontend/src/features/properties/tabs/PricingTab.tsx` (`PricingTab` at :173;
  in-file `SeasonsList` :37, `ExtrasTable` :105, `DiscountsTable` :139 — all
  private to this file)
- `frontend/src/features/properties/components/RatePlanDetailPanel.tsx`
  (`RatePlanDetailPanel` :179, exported `ActiveBadge` :30, private
  `RatePeriodBlock` :39 — referenced **only** by `PricingTab` + its own test)
- `frontend/src/features/properties/tabConfig.ts:5` (`{ slug: "pricing",
  labelKey: "tabs.pricing" }`)
- `frontend/src/app/router.tsx:171-176` (`path: "pricing"` → `PricingTab`)
- `frontend/src/i18n/locales/{en,el}/properties.json` — `tabs.pricing` label +
  the orphaned slice of the `pricing.*` copy tree (see Unit 3 caveat: much of
  `pricing.*` is still used by the shared dialogs)
- tests: `PricingTab.test.tsx`, `RatePlanDetailPanel.test.tsx`,
  `RatePlanFormDialog.test.tsx` (all under
  `frontend/src/features/properties/__tests__/`)

Kept & reused (shared between old tab and Workbench — **do not delete**):
- `frontend/src/features/properties/components/RatePlanFormDialog.tsx`
  (`RatePlanFormDialog` :82) — today referenced only by `PricingTab`, but it is
  the season create/edit form the Workbench is **missing**; Unit 1 reuses it.
- `frontend/src/features/properties/components/RatePeriodFormDialog.tsx`,
  `RateBandFormDialog.tsx` — already used by the Workbench.
- `frontend/src/features/properties/{hooks,api,schemas}.ts` — the rate/period/
  band/extra/discount hooks, fetchers and Zod schemas are shared. In particular
  `useCreateRatePlan`/`useUpdateRatePlan`/`useDuplicateRatePlan`/
  `useDeleteRatePlan`/`useDeleteRatePeriod` already exist (`hooks.ts` :288/303/
  326/316/362) and back `POST /properties/{id}/rate-plans`,
  `PATCH /rate-plans/{id}`, `POST /rate-plans/{id}:duplicate`,
  `DELETE /rate-plans/{id}`, `DELETE /periods/{id}` (`api.ts` :287/295/307/303/
  328).
- `frontend/src/features/properties/coverage.ts` (`formatPartyGaps`).

The Workbench (rename + parity target):
- `frontend/src/features/rate-workbench/` — `RateWorkbenchPage.tsx` (page,
  season picker at :233-255, `RatePeriodFormDialog` create-only at :291-304),
  `components/MatrixEditor.tsx` (band CRUD + add-period CTA; **no** period
  edit/delete), `components/InspectorPanel.tsx` (extras/discounts/inclusions
  CRUD), `components/PriceProbePanel.tsx` (live probe), `components/
  WorkbenchTimeline.tsx`, `toLanes.ts`, `hooks.ts`, `api.ts`, `schemas.ts`.
- Tab registration: `frontend/src/features/properties/tabConfig.ts:6`
  (`{ slug: "rate-workbench", labelKey: "tabs.rate_workbench" }`);
  `frontend/src/app/router.tsx:177-183`; visibility gate (writer-only)
  `frontend/src/features/properties/PropertyDetailLayout.tsx:27-31`.
- User-facing "Workbench" strings (rename inventory):
  - tab label `tabs.rate_workbench` = **"Rate Workbench"** —
    `en/properties.json:62` (el `:62`)
  - page H1 `rate_workbench.title` = **"Rate & Service Workbench"** —
    `en/properties.json:1039` (rendered `RateWorkbenchPage.tsx:98`) + a
    `rate_workbench.preview_badge` "Preview" chip (`:1041`, rendered :99)
  - `rate_workbench.subtitle` (`:1040`), `rate_workbench.error.title`
    ("Couldn't load the workbench", `:1065`)

## The supersession (why the old tab goes)

Both tabs edit the same tree. The Workbench is a **strict superset** of the old
tab everywhere except rate-plan and rate-period *lifecycle*:

| Capability | Old "Pricing" tab | Rate Workbench (today) |
|---|---|---|
| View seasons (plans) w/ dates, currency, basis, active | ✅ list + drill-in fact list | ✅ timeline lane + season picker |
| **Create** a rate plan / season | ✅ `RatePlanFormDialog` | ❌ **missing** |
| **Edit** plan fields (name, currency, `price_basis`, effective_from/to, active, notes) | ✅ | ❌ **missing** |
| **Duplicate** a plan (`:duplicate`, copy a year's sheet → next year) | ✅ | ❌ **missing** |
| **Delete** a plan | ✅ | ❌ **missing** |
| Create a rate period | ✅ | ✅ (`RatePeriodFormDialog`, create only) |
| **Edit** a period (name, dates, min/max nights, active) | ✅ | ❌ **missing** |
| **Delete** a period | ✅ | ❌ **missing** |
| Rate bands: add / edit / delete + POA + net↔gross hint | ✅ | ✅ matrix (inline price edit + dialogs) |
| Coverage-gap (uncovered party) warnings | ✅ | ✅ (also clickable to fill) |
| Extras: manage | ⚠️ **read-only table** | ✅ full CRUD (inspector) |
| Discounts: manage | ⚠️ **read-only table** | ✅ full CRUD (inspector) |
| Inclusions / services | ❌ | ✅ (inspector, GAP-037) |
| Whole-year timeline w/ price-tier bands | ❌ | ✅ |
| Live guest-side price probe (owner economics) | ❌ | ✅ |

So the Workbench already beats the old tab on bands, extras, discounts,
inclusions, timeline and probe. The **only** modeling capabilities the old tab
has that the Workbench lacks are the six ❌ rows: rate-plan create/edit/
duplicate/delete and rate-period edit/delete. Those must be closed **before**
deletion — the stub's "must not degrade modeling capabilities for end user"
requirement made concrete.

The sharpest consequence: because the Workbench has **no** rate-plan create
path (no `useCreateRatePlan`/`RatePlanFormDialog`; the zero-season empty state
at `RateWorkbenchPage.tsx:199-205` is a passive `EmptyState` with no action), a
property with no rate plans **cannot be bootstrapped from the Workbench at all**
— today you must use the old Pricing tab (or the API) to create the first plan.
Deleting the old tab without Unit 1 would leave new properties un-priceable
through the UI. This is the load-bearing reason Unit 1 precedes Unit 3.

## Plan

Four units. Units 1 → 2 → 3 are ordered (parity must precede deletion; rename
before delete is cosmetic-safe either way but keeps the diff readable). Each
unit is independently test-backed and must leave the FE quality gate green
(`npm run lint && npx prettier --check . && npx tsc -b --noEmit && npx vitest
run`).

### Unit 1 — close the parity gap in the Workbench (rate-plan + rate-period lifecycle)

Bring the six missing affordances into the Workbench, reusing the existing
shared dialogs and hooks — **no new endpoints, no new form components**.

- **Rate-plan (season) lifecycle.** Add an "Add season" affordance and per-
  season Edit / Duplicate / Delete on the Workbench. Natural home: a season
  header/toolbar row next to the existing season picker
  (`RateWorkbenchPage.tsx:233-255`), or an actions cluster on each seasons-lane
  band. Wire the existing `RatePlanFormDialog` (create + edit modes) and
  `useCreateRatePlan` / `useUpdateRatePlan` / `useDuplicateRatePlan` /
  `useDeleteRatePlan`. Duplicate is the highest-value one — it copies an entire
  year's rate sheet forward (the primary way owners roll rates year-on-year);
  losing it would be the worst regression. Delete uses a `ConfirmDialog`
  (mirror `PricingTab.tsx:210-225,288-327`).
- **Rate-period edit + delete.** The Workbench creates periods but can't edit or
  delete them (`RateWorkbenchPage.tsx:291` is `mode="create"` only; `MatrixEditor`
  has no period dialog). Add per-period Edit (open `RatePeriodFormDialog` in
  `mode="edit"`) and Delete (`useDeleteRatePeriod` + confirm) — put the controls
  on each period row of the matrix (`MatrixEditor.tsx`, the `periodLabel` row at
  :234) so period metadata (name, dates, min/max nights, active) is editable
  where the period is shown. Reference the old tab's wiring in
  `RatePlanDetailPanel.tsx` (:208 delete, :212/330-345 edit).
- Keep all write affordances behind `useHasReservationsRole()` — buttons
  **disable inside a tooltip**, never disappear (frontend CLAUDE.md role-gating).
- Preserve the plan-level currency-mismatch warning the old tab shows via
  `RatePlanDetailPanel` (GAP-026) — it comes along with `RatePlanFormDialog`; if
  it doesn't surface on the plan row, add the same soft warning.
- **Tests.** The Workbench leaf components are already covered by colocated
  tests (`MatrixEditor.test.tsx`, `InspectorPanel.test.tsx`,
  `PriceProbePanel.test.tsx`, `ExtraFormDialog.test.tsx`,
  `DiscountFormDialog.test.tsx`, `QuoteResultCard.test.tsx`, plus
  `matrixModel`/`coverageGaps`/`toLanes`/`writeSchemas`/`timelineLayout`/
  `TimelineBand` unit tests) — there is **no** rate-plan/period lifecycle
  coverage yet because the affordances don't exist. Add tests for the new flows:
  season create/edit/duplicate/delete round-trips, period edit + delete-with-
  confirm, and role-gating (disabled-with-tooltip when not a writer). Port the
  intent of the soon-to-be-deleted `PricingTab.test.tsx` /
  `RatePlanDetailPanel.test.tsx` / `RatePlanFormDialog.test.tsx` season+period
  assertions rather than dropping them on the floor.

### Unit 2 — rename the user-facing "Workbench" → "Rates"

Scope decision (recommended): **rename user-facing copy only; leave the slug,
route, folder, symbol names and `rate_workbench.*` i18n-key namespace as internal
identifiers.** Rationale — KISS: the churn of renaming the `rate-workbench/`
folder, `RateWorkbenchPage`/`WorkbenchTimeline`/`WorkbenchBand` symbols, the
route/slug and the entire `rate_workbench.*` key tree (dozens of `t()` call
sites across ~12 files + the JSON) buys nothing the user sees, and risks a large
error-prone diff. Do the two-string user-facing rename now; treat the
identifier rename as optional hygiene (a follow-up SMELL if ever wanted).

- `tabs.rate_workbench`: "Rate Workbench" → **"Rates"** (en + el).
- `rate_workbench.title`: "Rate & Service Workbench" → **"Rates"** (or
  "Rates & services" if we want to keep signalling the inclusions/extras scope —
  pick one; en + el). Decide whether to keep the "Preview" badge
  (`rate_workbench.preview_badge`) — once this is the *only* rates tab it is no
  longer a preview; recommend dropping the badge (`RateWorkbenchPage.tsx:99` +
  the key).
- Update `rate_workbench.error.title` ("Couldn't load the workbench") to match.
- Leave test IDs, slugs and enum/route strings literal per the i18n rules.

Note the alternative for the record: a full rename (slug `rate-workbench` →
`rates`, folder/symbols, key namespace) — larger, deferred unless the user wants
it.

### Unit 3 — delete the old "Pricing" tab and its now-dead code

Only after Unit 1 has landed the parity affordances.

- Delete `PricingTab.tsx` and `RatePlanDetailPanel.tsx` (incl. exported
  `ActiveBadge` — confirm no other importer first) and their three test files.
- **Do NOT delete `RatePlanFormDialog.tsx`** — Unit 1 now depends on it.
- Remove the `pricing` entries from `tabConfig.ts:5` and `router.tsx:171-176`.
- **Stale-bookmark redirect:** staff may have `/properties/:id/pricing`
  bookmarked. Add a redirect from `pricing` → `rate-workbench` in `router.tsx`
  (a small `<Navigate>`), rather than letting it 404. (Cheap; skip only if the
  team prefers a hard 404.)
- **i18n cleanup, carefully:** remove `tabs.pricing`, but the `pricing.*` copy
  subtree is **partly shared** — `RatePlanFormDialog`, `RatePeriodFormDialog`
  and `RateBandFormDialog` all consume `pricing.*` keys too. Remove only keys
  referenced **solely** by the deleted `PricingTab`/`RatePlanDetailPanel`
  (grep each key before deleting); leave the rest.
- Update `PropertyDetailLayout.test.tsx` if it asserts the tab list contains
  "pricing".
- Update the stale doc comment `rate-workbench/hooks.ts:23` that references
  "`PricingTab`'s `RatePlanDetailPanel`" (cache-dedup context) now that
  `PricingTab` is gone.

### Unit 4 — docs close-out

- If the design package documents the property-admin tab set (property FE spec /
  workflows), update it to a single "Rates" tab and drop the old Pricing tab.
- `✅ RESOLVED` banner on this file (problem / fix / commit), `git mv` to
  `done/`, flip the row in `INDEX.md`.

## Acceptance

- The Workbench ("Rates" tab) can **create, edit, duplicate and delete** a rate
  plan / season, and **edit and delete** a rate period — verified by tests; no
  rate-modeling capability the old Pricing tab had is lost (the parity table's
  six ❌ rows are now ✅).
- Duplicate-season still copies a full year's rate sheet forward (the
  `:duplicate` round-trip) from the new UI.
- Only **one** rate-editing tab exists on the property page, labelled **"Rates"**
  (en + el); the "Rate Workbench" / "Rate & Service Workbench" strings are gone
  from user-facing copy; no "Pricing" tab remains.
- `PricingTab.tsx` / `RatePlanDetailPanel.tsx` and their tests are deleted;
  `RatePlanFormDialog.tsx` and all shared period/band/extra/discount code
  remain; no dangling imports.
- Navigating to a stale `…/pricing` URL lands on the Rates tab (or a deliberate
  404 if the team chose that).
- No orphaned i18n keys; no `pricing.*` key still referenced by a shared dialog
  was removed.
- Full FE quality gate green (`eslint`, `prettier --check`, `tsc --noEmit`,
  `vitest`).

## Dependencies

- **[GAP-059](gap-059-rate-period-name-compulsory.md)** (`RatePeriod.name`
  compulsory) is a natural sibling: the Workbench matrix already falls back to a
  date-range label when a period has no name (`MatrixEditor.tsx:31-33`), and
  GAP-059 wants names required "for a meaningful UI presentation of date bands".
  Not a hard blocker, but if GAP-059 lands first the period edit/create dialogs
  in Unit 1 should treat `name` as required to match the model. Sequence GAP-059
  before or with this ticket's Unit 1 if convenient.
- Builds on [[project_rate_workbench]] (the Workbench itself),
  [[project_gap056_rate_restructure]] (period-native model) and SMELL-019
  (`RateBand` naming). No interaction with the pricing engine or any backend
  contract — this is entirely a frontend consolidation.
- GAP-025 (changeover-aware end-date suggestion) rides inside
  `RatePeriodFormDialog`, so it keeps working for period edit as well as create.
