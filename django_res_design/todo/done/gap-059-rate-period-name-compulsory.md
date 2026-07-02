> **✅ RESOLVED (2026-07-02)** — shipped on `feat/gap-059` in four units:
> (1) `pricing.services.period_names.derive_period_name` (compact en-dashed
> date span, fixed-English/deterministic) + the legacy loader names every
> synthesized period; (2) model field required + CHECK
> `rateperiod_name_not_blank`, migration `pricing.0017` (backfill incl.
> whitespace-only rows → AlterField → AddConstraint), factory + ~40 test
> sites named; (3) FE write schema `.min(1)` (i18n key en+el), dialog label
> drops "(optional)", live date-span name suggestion (never clobbers typed
> input, revalidates after a failed submit); (4) one shared `periodLabel()`
> fallback replaces the five divergent renderings, `untitled` key deleted,
> docs errata. Two deviations from the plan above, both improvements:
> **carry-forward copies the curated source-period name** when a segment's
> bands unanimously descend from one source period (date-span placeholder
> only for mixed-parentage segments) — better than the placeholder-always
> recommendation; and decision 2's "collision-free within a plan" claim is
> only true within a calendar year (two periods with the same day-span in
> different years share a placeholder) — accepted: names are editable,
> non-unique labels. FE suggestion is locale-aware (Greek months under `el`)
> while backend placeholders are fixed-English — deliberate.

# GAP-059 — `RatePeriod.name` should be compulsory

- **Severity:** Gap (data-quality / UI-presentation; the field exists but
  nothing enforces it, so real data is mostly blank)
- **Source:** stub added 2026-07-02 during the rate-workbench supersession
  review (same batch as GAP-060). Motivation: a meaningful UI presentation of
  date bands needs every period to carry an operator label.
- **Blocks:** nothing hard — but every unnamed period degrades the workbench
  timeline, the matrix, the probe result card, and the Pricing tab into
  three *different* fallback renderings (see Problem), and Q-018's
  carry-over will copy whatever periods contain, blanks included.
- **Files:**
  - `django_res/pricing/models/rate.py:78` (`name = CharField(max_length=128,
    blank=True, default="")`; docstring :69–70 calls it "an optional operator
    label")
  - `django_res/pricing/serializers/rate.py:149-253` (`RatePeriodSerializer` —
    `name` in fields :161–172, not in `read_only_fields`, `validate()` never
    touches it → DRF renders it `required=False`)
  - `django_res/pricing/migrations/` (next migration: backfill + `AlterField`
    + CHECK; `0013_rateperiod_hierarchy.py:59` created the column blank-default)
  - `django_res/data_migration/loaders/pricing.py:691-696`
    (`RateBandLoader._load_rows` creates periods **without** `name` — every
    legacy-migrated period is blank; legacy has no period-name column, the
    period axis is synthesized from `VillaSeasonRate` span segmentation)
  - `django_res/pricing/factories.py:57-72` (`RatePeriodFactory` doesn't set
    `name`; `django_get_or_create=("plan","date_from","date_to")`)
  - `django_res/seeding/_pricing_helpers.py:150-184` (only path that *does*
    name periods: `_SEASONS` Low/Mid/Peak)
  - `frontend/src/features/properties/schemas.ts:378,398` (read
    `name: z.string().nullable().optional()`; write `.trim().max(128)
    .optional()` — no `.min(1)`, unlike every sibling entity)
  - `frontend/src/features/properties/components/RatePeriodFormDialog.tsx:50,77,152-156`
    (shared create/edit dialog — Pricing tab *and* workbench; label copy is
    literally "Name (optional)", `createDefaults()` seeds `name: ""`)
  - `frontend/src/features/rate-workbench/RateWorkbenchPage.tsx:67-76,141-147,291-304,343-353`
    (four create-prefill paths, none seed a name; probe `periodLabels`)
  - `frontend/src/features/rate-workbench/toLanes.ts:112-116,232`;
    `components/MatrixEditor.tsx:31-33,237-239,270-274`;
    `components/QuoteResultCard.tsx:73`;
    `frontend/src/features/properties/components/RatePlanDetailPanel.tsx:66`
    (the divergent empty-name fallbacks)

## Problem

GAP-056 introduced `RatePeriod` with `name` as "an optional operator label",
and every layer since has faithfully kept it optional — with the result that
in practice **almost no period has a name**:

1. **Legacy data: 100% blank.** `RateBandLoader` synthesizes periods from
   `VillaSeasonRate` date-span segmentation and never sets `name`
   (`pricing.py:691-696`). There is no legacy column to draw from — the
   legacy season *name* lands on `RatePlan.name`, not the period. Every
   migrated period will arrive at cutover blank.
2. **Workbench-created data: blank by default.** All four workbench create
   paths (matrix "Add period" header button, matrix empty-state CTA,
   coverage-gap lane click, per-period "+" add-after) prefill only
   `planId`/dates; the dialog labels the field "Name (optional)" and nothing
   validates it. The fast gap-fill flow routinely produces unnamed periods.
3. **The UI papers over the blanks three different ways.** Timeline rates
   lane falls back to the *plan* name (`toLanes.ts:232`); the matrix rows and
   gap warnings and the probe label fall back to the *date range*
   (`MatrixEditor.tsx:31-33`, `RateWorkbenchPage.tsx:343-353`); the Pricing
   tab shows the literal string *"Untitled period"*
   (`RatePlanDetailPanel.tsx:66`); the matrix row's inline name span renders
   *nothing* (`MatrixEditor.tsx:237-239`). Same entity, four renderings.

The premise of the stub holds: the workbench's whole-year timeline and the
matrix are date-band presentations, and a band labelled by its own dates (or
by its parent plan's name, or "Untitled period") tells the operator nothing.
The fix is to make the label compulsory at the write surface and structurally
in the DB, backfill the existing blanks with a deterministic placeholder, and
collapse the FE fallbacks to one shared rule.

## Decision points (recommendations inline)

1. **Enforcement depth — app-only vs structural.** Recommend **structural**:
   drop `blank=True, default=""` from the model *and* add a
   `CheckConstraint(name <> '')`. Precedent: GAP-056 itself chose structural
   enforcement (two `btree_gist` EXCLUDEs) for this exact model family;
   SMELL-014 converted an app-level guard to structural. The app-level-only
   precedent (GAP-029) was a cross-field disjunction that SQL expresses
   awkwardly — this is a single-column non-empty check, the easy case.
   Removing `default=""` matters: DRF's ModelSerializer keeps a field
   `required=False` while the model has a default, so the serializer becomes
   `required=True, allow_blank=False` *automatically* once the model is
   fixed (DRF CharField also trims whitespace by default, so whitespace-only
   names are rejected for free at the API; the DB CHECK stays the simple
   `<> ''` — `btrim()` hardening not worth it, KISS).
2. **Backfill / loader placeholder derivation.** Migrated rows have no
   meaningful name available anywhere; any backfill is a placeholder whose
   job is to satisfy the invariant and read acceptably until an operator
   renames it. Recommend the **exact inclusive date span, day precision** —
   e.g. `3 Jul – 21 Aug`, collapsing to `3 – 21 Jul` within one month —
   because it is deterministic (loader idempotency), collision-free within a
   plan (periods are disjoint), and matches what the matrix fallback already
   shows operators today, so cutover changes nothing visually. Rejected
   alternatives: month-only spans ("Jul – Aug") collide when two periods sit
   inside one month; `{plan.name} {n}` ordinals add no information and go
   stale on reorder. One shared helper, used by both the backfill migration
   and the loader.
3. **Read-schema tightening.** Keep the FE *read* schema tolerant
   (`nullable().optional()` stays) — a hard `.min(1)` on reads would brick
   the whole workbench page against any stray blank row. Enforcement is for
   writes; display keeps exactly one defensive fallback (the same date-span
   rule as decision 2).

## Plan

Backend first (the contract change), then FE, then docs. Four small
test-backed units.

### Unit 1 — model + API enforcement, backfill, factory

- `pricing/models/rate.py`: `name = models.CharField(max_length=128)` (drop
  `blank=True, default=""`); docstring :69–70 reworded — the label is
  required, still no grouping semantics (season *tiers* are Q-022, separate).
- Migration `0017` (single file, ordered ops): `RunPython` backfill deriving
  the date-span placeholder for every `name = ''` row → `AlterField` →
  `AddConstraint(CheckConstraint(name <> ''))`. Reverse: drop constraint +
  re-relax field (backfilled names stay — they're valid data).
- `RatePeriodSerializer` needs no required-ness code (falls out of the model
  change) — add tests pinning the new contract: POST without `name` → 400
  keyed on `name`; POST `name: ""` / `"   "` → 400; PATCH clearing to blank →
  400; PATCH omitting `name` still fine (partial update).
- `RatePeriodFactory` gains a deterministic name (e.g.
  `factory.Sequence(lambda n: f"Period {n}")`); natural key
  `("plan","date_from","date_to")` unchanged. Any test doing bare
  `objects.create` without a name now trips the CHECK — fix at the factory,
  not per-test.
- seed_dev untouched (`_pricing_helpers` already names Low/Mid/Peak).

### Unit 2 — legacy loader synthesizes names

- **Read `data_migration/CUTOVER.md` first** (package must stay idempotent).
- `RateBandLoader._load_rows` (`pricing.py:691-696`): add
  `name=<date-span helper>(seg.date_from, seg.date_to)` to the
  `RatePeriod.objects.create(...)` call. The helper is pure on the segment
  dates, so re-runs reproduce identical rows — idempotency preserved; the
  `legacy_id=f"{plan.legacy_id}:p{i}"` keying is untouched.
- `test_rate_band_loader.py`: assert created periods carry the derived name.
- Reconcile checks unaffected (they compare prices/spans, not names) — note
  in the commit, don't touch.

### Unit 3 — FE: required in the dialog, all four create paths still fluent

- `schemas.ts:398`: write schema → `z.string().trim().min(1, …).max(128)`
  (now matches every sibling entity's posture). Read schema **unchanged**.
- `RatePeriodFormDialog.tsx`: label drops "(optional)" (en + el); the
  existing error-render slot (:157–161) starts firing — wire the `.min(1)`
  message through i18n (en + el).
- Friction offset for the fast flows: the coverage-gap click and add-after
  "+" prefills (`TimelineBand.tsx:48-50,80-84`) additionally seed
  `name: <date-span suggestion>` from the prefilled dates — editable, but
  the operator can accept-and-save in one keystroke like today. The two
  matrix "Add period" paths prefill dates only a day-anchor, so they get the
  suggestion too once dates are set — keep it simple: derive the suggestion
  in `createDefaults()` from `initialValues` when both dates are present.
- Vitest: dialog blocks save on empty name; each of the four openers
  produces a savable prefill.

### Unit 4 — FE fallback collapse + docs

- One shared `periodLabel(period)` helper (date-span fallback, defensive
  only): replaces the plan-name fallback in `toLanes.ts:232`, the local
  `periodLabel` in `MatrixEditor.tsx:31-33`, the probe map in
  `RateWorkbenchPage.tsx:343-353`, and the "Untitled period" branch in
  `RatePlanDetailPanel.tsx:66`. Delete the `pricing.rate_period.untitled`
  key (en + el). `QuoteResultCard`'s "Best available rate" default stays —
  that's the *no winning period* case (projected/no match), not an unnamed
  one.
- Update the fixtures that encode blankness: `matrixModel.test.ts:17-25`
  (`name: ""` factory) and the `toLanes.test.ts:291` "falls back to the plan
  name" test (retarget to the new helper's behaviour).
- Docs: `04-pricing.md` / `data-model-overview.md` /
  `product-design/04-rest-api-surface.md` are stale **pre-GAP-056** (still
  describe `RateCard`/`RateRule`, no `RatePeriod` at all) — full re-write is
  out of scope here; add the required-name statement wherever the period
  model *is* documented (GAP-056's done-file model sketch + the model
  docstring in Unit 1) and leave a one-line errata pointer in `04-pricing.md`.
- INDEX flip.

## Hazards

- **API contract break:** `POST /rate-plans/{id}/rate-periods` and
  `PATCH /periods/{pk}` start 400-ing on missing/blank name. Only consumer
  is our SPA (Unit 3); land backend + FE in the same push to local main.
- **Deploy/backfill window:** the CHECK lands in the same migration as the
  backfill, so no window where old code writes blanks into a constrained
  table exists within a deploy; anything writing periods outside the
  serializer (admin, shell) gets the model/DB guard.
- **Loader re-runs:** derivation is pure on segment dates → idempotent; if
  the date-span helper's format is ever changed after a load, a re-run would
  rewrite names — acceptable pre-cutover, note in CUTOVER.md if touched.
- **Admin forms:** `RatePeriodAdmin` starts requiring the field
  (blank=False) — desired, no action.

## Acceptance

- DB: `CheckConstraint rateperiod_name_not_blank` present; zero `name = ''`
  rows after migrating a legacy-loaded database; `objects.create()` without
  a name raises `IntegrityError`.
- API: create/blank/whitespace/clear-on-PATCH all 400 keyed on `name`;
  partial PATCH omitting `name` unaffected; existing period tests green.
- Loader: `test_rate_band_loader` asserts derived names; migration package
  re-run reproduces identical names; reconcile output unchanged.
- FE: dialog requires a name (en + el error copy), all four workbench create
  paths save fluently via the date-span suggestion; exactly one fallback
  code path remains (`periodLabel` helper); `untitled` i18n key gone;
  vitest + pytest suites green.
- Docs: model docstring + GAP-056 done-file sketch state the field is
  required; errata pointer in `04-pricing.md`; INDEX updated.

## Dependencies

- **GAP-060 (kill old Pricing tab):** `RatePeriodFormDialog` is shared
  between the old tab and the workbench, so Unit 3 covers both surfaces in
  one change; no ordering constraint either way. If GAP-060 lands first,
  `RatePlanDetailPanel.tsx` (Unit 4) may already be gone — re-scope, don't
  re-add.
- **Q-022 (season tiers):** the future controlled `season_tier`
  enum is a *reporting category*; `RatePeriod.name` stays the free-text
  per-villa operator label. Do not conflate — this ticket deliberately adds
  no uniqueness or vocabulary constraint on `name`.
- **Q-018 (rate reductions / carry-over):** the 8-unit build plan copies
  periods forward; once `name` is compulsory the copy must carry it (it
  copies the base row wholesale, so it should for free — assert it in that
  build's tests).
- **GAP-056 / SMELL-019:** done — this is a residual of the "optional
  operator label" call made there.
