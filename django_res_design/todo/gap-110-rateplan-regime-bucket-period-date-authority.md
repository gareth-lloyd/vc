# GAP-110 — `RatePlan` becomes a dateless regime bucket; `RatePeriod` is the sole date authority; legacy seasons load as one plan per villa + currency

- **Severity:** 🟠 Gap (build). Adopts SPEC-001's recommended direction as
  a committed change, with the loader half that the exploration did not
  have data for. Behaviour changes at the plan-selection boundary only; the
  per-night pricing maths are untouched.
- **Source:** 2026-09-11 legacy-loader audit (BUG-028 §5 parity gap) and
  the follow-up design pass the same day (three explorations: backend
  envelope readers, frontend envelope readers, legacy `VillaSeasonDates`
  vs `VillaSeasonRate` profile on the 24-Apr-2025 dump + the
  `villacollective_loaderaudit` scratch DB). SPEC-001 (2026-07-03) is the
  reasoning this builds on; it stays as the record of alternatives
  considered and rejected.
- **Files touched:**
  - `pricing/models/rate.py:58-59` — `RatePlan.effective_from/effective_to`
    (to drop); `:68` `Meta.ordering = ["property", "-effective_from"]`;
    `:81` the `(effective_from, effective_to)` index; `:102-113` `RatePeriod`
    (gains `property`, `currency`); `:132-145` `rateperiod_no_overlap`
    (partition widens from `plan` to `property, currency`).
  - `pricing/services/engine.py:575-622` — `_load_real_context`, the one
    place the envelope decides coverage (`:591-598`). Nothing else in the
    engine reads it: the per-night loop (`:136-345`), `covering_bands`
    (`:459-539`) and `stay_length_bounds` (`:541-572`) ride the context it
    returns.
  - `pricing/services/currency.py:52-70` `pick_preferred_plan` (`:60`
    equality on `effective_from` is the tie-break key); `:87`
    `resolve_property_currency` (`effective_from <= today` cutoff).
  - `pricing/services/projection.py:219` (anchor filter
    `effective_from__lt=1 Jan target`), `:252` (`source_year =
    anchor.effective_from.year`), `:278-282` (synthetic `proj_plan`
    envelope).
  - `pricing/services/carryover.py:88` (idempotency key =
    `effective_from__year=target_year`), `:103` (`year_delta`), `:157-161`
    (writes the new plan's envelope with `keep_calendar_date`, while periods
    move by `date_map`, so a carried period can already land up to 3 days
    outside its own envelope).
  - `pricing/serializers/rate.py:448-449` — both fields writable on
    POST/PATCH; no `from <= to` validation anywhere backend
    (`RatePeriodSerializer.validate` `:311-425` never consults the plan
    window).
  - `pricing/admin.py:70` — `carry_forward_next_year` derives the target
    year from `effective_from`.
  - `seeding/_pricing_helpers.py:176-181` — asserts `effective_to` and
    partitions the envelope; `seeding/stages/properties.py:206-213` dates a
    second-currency plan one day earlier as a priority dial.
  - `data_migration/loaders/pricing.py:241-251` (`RatePlanLoader`: one
    plan per live `VillaSeason`; `:249-250` envelope =
    `MIN/MAX(VillaSeasonDates)` with no `DeletedAt` filter; `:272-273` the
    `date(2020, 1, 1)` / `NULL` fallback; `:311-312` envelope copied onto
    `PropertyService.applies_from/to`), `:135` `resolve_rate_band_overlaps`,
    `:617-655` period flattening via `pricing/services/flattening.py:107`.
  - `data_migration/management/commands/reconcile_legacy.py:240-242`
    (`RatePlan` count vs live `VillaSeason`).
  - `reservations/services/stay_options.py:150-155` — perf design assumes
    one `load_context()` per property "when a single plan spans the window".
  - Frontend: `features/properties/components/RatePlanFormDialog.tsx:228-257`
    (the only editable envelope inputs); `rate-workbench/toLanes.ts:378-398`
    + `coverageGaps.ts:19-36` (coverage lane clamps to the envelope);
    `rate-workbench/RateWorkbenchPage.tsx:203-218` (plan pick is already
    period-derived), `:596` + `components/CarryForwardDialog.tsx` (collects
    no dates; switches to the new plan on success);
    `features/properties/schemas.ts:677-678, 881-896`.
  - Docs: `design/backend/04-pricing.md` (§RatePlan fields `:82-83`,
    lifecycle `:72`, anchor `:296-300`), `design/decisions.md`,
    `data_migration/CUTOVER.md` / `COVERAGE.md`.

## Problem

### The envelope means nothing, and two load-bearing reads trust it

`RatePlan.effective_from/effective_to` is a bare, unvalidated date pair that
duplicates what the plan's periods already know. Nothing ties it to them:
not the model, not the serializer, not the loader, not carry-forward. The
engine uses it as a **plan-selection gate only** — once a plan passes the
whole-stay window test, every active period on it prices, envelope or not
(`engine.py:606-608` has no date filter). Projection and carry-forward read
its **year** to shift a whole grid. So an envelope that disagrees with its
periods either hides real prices (a stay is sent to projection or
`NoRateAvailable` although bands exist) or shifts a projected year by one.
Three smaller defects ride on the same field: the gate compares an inclusive
`effective_to` against the half-open checkout date, so a plan ending
31 Dec cannot price a stay checking out 31 Dec; `pick_preferred_plan`'s
same-currency tiebreak is a silent recency guess; and a legacy season
reused as a multi-year bucket (villa 161: one season, rates
2024-08 → 2026-11) projects two years of periods at once and resolves the
self-collision by lowest pk.

### What the legacy data says the envelope was

`VillaSeasonDates` was **never a pricing input** in legacy. `ModifyRates`
(`PropertyService.cs:1022-1038`) used it once, at data entry, to decide
which season a newly typed rate row belongs to (the window containing the
arrival date; save refused if none). Quote calculation, `sp_seasonRates`
and `RatesModel.Calculate()` read the rate rows only. Windows were then
rolled forward to the next year while old rate rows stayed behind, and
`COPY` cloned windows and rows together. That is exactly the shape the
loader reproduces:

| Scratch-DB load (24-Apr-2025 dump) | |
|---|---|
| `RatePlan` rows (one per live `VillaSeason`) | 521 |
| envelope = period union | 204 |
| envelope wider than periods | 236 |
| envelope narrower / partial / disjoint | 64 (23 / 40 / 1) |
| zero periods | 17 |
| open-ended envelope (the 2020-01-01 fallback) | 1 |
| `(property, currency)` pairs | 275 |
| pairs with > 1 plan | 170 (2 → 111, 3 → 48, 4 → 5, 5 → 6) |
| pairs whose **periods** collide across plans | 39 (102 period pairs, 25 plans) |
| pairs whose **envelopes** overlap | 16 |

Legacy side: 5,928 live priced rows on live villas; 237 entirely outside
their own season's window (236 before it, 1 after), 58 partial. By rate
year the out-of-window rows are 2023 ×255, 2024 ×490, 2025 ×7, **2026+ ×0**
— stale rows the window rolled away from, not future mispricing. Every
villa with rates has at least one window; 96% of seasons have exactly one.
Cross-season same-party overlaps: 298 pairs on 37 villas, the source of the
39 colliding pairs above. Every loaded plan is GROSS (the SMELL-021
reconcile invariant) and all but one villa price in a single currency: **in
regime terms each legacy villa has one regime**, and the 521 plans are
year buckets inherited from a table that was a data-entry convenience.

### Why the cheap fix is not enough

Binding the envelope to the period union (SPEC-001's interim) removes the
drift class but keeps the engine reading a scalar it should not need, keeps
the year-bucket plan grouping and its 39 cross-plan collisions, keeps the
silent same-currency tiebreak, and still leaves an empty plan with no
dates. The "empty plan loses its year" cost SPEC-001 worried about only
exists while a plan is read as a year; under the regime model nobody
creates "the 2028 EUR plan", they add 2028 periods to the EUR regime.

## Proposed fix

Build expand → migrate → contract, as GAP-056 was, so every commit stays
green. Production has no rate data until cutover, so the loader change
lands first and dev/scratch DBs are reloaded; no data migration of live
plans is needed.

### U0 — Loader: one plan per villa + resolved currency

- `RatePlanLoader` groups live priced `VillaSeasonRate` rows
  (`DeletedAt IS NULL AND IsExTra <> 1`, live villa) by `VillaId` and
  resolved currency (row `CurrencyId`, else villa currency, else the
  BUG-028 §3 fallback), **not** by `SeasonId`. Expect ~276 plans.
  `legacy_id = f"villa:{VillaId}:{currency_code}"`; `name` = the villa's
  currency code + "rates" (or the single season name where a villa has
  one); `notes` lists the merged legacy seasons by id and name so nothing
  is lost.
- `RateBandLoader` feeds the whole villa+currency row set through
  `resolve_rate_band_overlaps` → `flatten_rate_grid` once, so the 298
  cross-season overlaps resolve with the same policy that already resolves
  within-season ones (CUTOVER-recorded, user-confirmed). Add an acceptance
  check that the resolved winner reproduces the legacy quote on a sample of
  `VillaQuotationMaster` rows for the 37 affected villas.
- Plan-level fields that used to come from the season
  (`prices_by_occupancy`, `fallback_nightly`, `price_basis`) are asserted
  uniform across the villa's merged seasons; a conflict fails loud (expect
  0 on this dump).
- `PropertyService.applies_from/to` (GAP-037 inclusions) take their band
  from the **live** `VillaSeasonDates` rows of the legacy season that
  carried the inclusion text, filtered on `DeletedAt` (95 deleted rows
  today), not from the plan.
- Expected losses recorded in `CUTOVER.md`: 17 rate-less seasons, 25
  windows with no rates, season names demoted to notes.
- `PropertyFinance.season` (`properties/models/finance.py:66-72`, a legacy
  carry-over FK to `RatePlan`) repoints to the merged plan; check whether
  anything still reads it and drop it if not.
- `reconcile_legacy`: `RatePlan` count = distinct (live villa, currency)
  with ≥ 1 loaded period; add the **night-parity invariant** — per villa,
  the set of dates carried by a live non-discount priced legacy row equals
  the set of dates covered by loaded periods (expected gap 0, reasons
  listed if not). This is the check the envelope never gave.

### U1 — `RatePeriod` carries `property` + `currency`; plan currency immutable

- Add nullable `property` and `currency` FKs to `RatePeriod`, backfill from
  `plan`, then make them non-null. `RatePeriod.save()` always sets both
  from `self.plan` (never accepted from input), so the copy cannot drift
  by any ORM path. Bulk paths that bypass `save()` are the only hole; the
  loader uses `objects.create`.
- `RatePlan.currency` becomes immutable once the plan has periods
  (serializer + model `clean`). Currency is the regime's identity; changing
  it is "create a new plan".

### U2 — The invariants

- Widen `rateperiod_no_overlap` to partition on `(property, currency)`:
  **at most one regime prices any night in a given currency**. Stays an
  `ExclusionConstraint` in `Meta` (SMELL-022), ungated by `is_active`,
  matching today's per-plan constraint (an inactive period still blocks;
  to re-price those nights, edit or hard-delete the period — permitted, no
  FK from `Booking`).
- New partial `UniqueConstraint`: **at most one active plan per
  `(property, currency, price_basis)`**. This is the guard against the
  legacy habit of "make a new season every year": a second same-regime
  plan is rejected at creation with "this villa already has an active EUR
  gross plan — add periods to it or carry forward", so the U3 two-regime
  error can only arise from a genuine basis or currency switch.
- Requires U0 first: the current load has 102 colliding period pairs.

### U3 — Engine selects periods, then infers the plan

Rewrite `_load_real_context` (~50 lines) to: fetch active periods for the
property (and currency, when given) whose inclusive range overlaps the
stay's nights; group by plan.

- **One plan** → that plan is the context, exactly today's triple.
  Uncovered nights use `fallback_nightly` or raise `NoRateAvailable`, as
  today.
- **No period on any night** → return `None` → projection, as today for
  "no covering plan".
- **Two plans** → raise a new, named `MultiRegimeStay` (subclass of
  `NoRateAvailable` so existing catch sites degrade safely) with a
  staff-readable message. A stay half under GROSS and half under NET has no
  single price basis (`_derive_commission_and_tax` is a per-stay
  singleton), so any automatic answer is a wrong number. Today the same
  situation silently prices under the newest plan and fallback-fills or
  fails the rest.
- The half-open/inclusive mismatch disappears with the gate; add the
  31 Dec checkout regression test.
- **Gap policy (SPEC-001 open decision 2):** a stay with *some* real nights
  prices real + fallback / fails; a stay with *no* real nights projects.
  One rule for within-year and out-of-year gaps. This is the one place a
  quote for a given dataset changes: a stay inside a partly-priced year on
  unpriced dates projects a guide instead of failing.
- `pick_preferred_plan`: the same-currency recency tiebreak becomes
  unreachable (U2) and is deleted; cross-currency ties still resolve by
  `settings_currency(property)`, then lowest pk. `resolve_property_currency`
  becomes "currency of the plan with an active period covering today, else
  the plan with the most recent period before today".
- `stay_options.py:150-155`: the one-load-per-property fast path now holds
  whenever one regime spans the window, which is almost always; update the
  comment.

### U4 — Projection and carry-forward anchor on a period year

- `find_anchor_plan` → `find_anchor_year(property, currency, target_year)`:
  the latest calendar year `< target_year` with at least one active period
  carrying an approved band, for that property + currency. Source periods
  are those overlapping `[1 Jan Y, 31 Dec Y]`; `year_delta = target − Y`.
  Fixes the multi-year-bucket double projection. The synthetic `proj_plan`
  stops carrying an envelope; `projection` provenance keeps `source_year`.
- `RateCarryoverService.materialise` writes the mapped periods **into the
  anchor's plan** (same regime) instead of creating a plan. Idempotency:
  refuse (or return the existing rows) when the target year already has an
  active period for that property + currency. The 3-day `date_map` vs
  `keep_calendar_date` drift goes away because no envelope is written.
  Carry Q-022's tier with the period when it exists.
- `admin.carry_forward_next_year` takes the target year from the plan's
  latest period year + 1.

### U5 — API, frontend, seeding

- `RatePlanSerializer`: drop both fields; `RatePeriodSerializer` unchanged
  except the U2 error surfaces as a 400 with the constraint's message.
- `RatePlanFormDialog`: remove the two date inputs and the ordering refine;
  the dialog is now name / currency / basis / occupancy mode / fallback.
- Coverage lane: `coverageGaps` clamps to the year window instead of the
  envelope (unpriced days in the visible year); `toLanes` no longer skips a
  plan by envelope.
- `CarryForwardDialog`: stays on the current plan after success and
  re-fetches (it already collects no dates; `useYearWindow` already drives
  the target year).
- Plan `<Select>` in the workbench becomes, in effect, a regime selector;
  label it by currency + basis. The year picker is already URL-driven and
  the plan auto-pick is already period-derived (`RateWorkbenchPage.tsx:203-218`), so no scoping change.
- Seeding: `_pricing_helpers` partitions an explicit year range; the
  one-day-earlier priority dial in `stages/properties.py:206-213` is
  replaced by the U3 currency rule (settings currency wins ties).
- Rewrite the ~60 backend test lines across ten files that set or assert
  the envelope (densest: `test_carryover.py`, `test_projection.py`,
  `test_engine_currency_optional.py`) and the FE tests listed under Files.

### U6 — Contract + docs

- Drop `effective_from`, `effective_to`, the index, `Meta.ordering` →
  `["property", "pk"]`; drop the audit-track entries in `pricing/apps.py`.
- `04-pricing.md`: plan field list, lifecycle paragraph (retire = period
  `is_active` or plan `is_active`, no "set `effective_to` in the past"),
  anchor rule, gap policy. `decisions.md`: one row (regime bucket adopted,
  one plan per villa+currency at cutover, two-regime stay is an error, gap
  policy). `CUTOVER.md` / `COVERAGE.md`: loader regrouping + expected
  losses. SPEC-001 → `done/` with a pointer here.

## Acceptance

- Cross-producer equivalence tests pass unchanged for every stay that has
  real coverage under one plan: quotes are identical before and after.
  (test)
- A stay checking out on the last day of a priced period prices. (test)
- A stay touching periods of two plans in one currency raises
  `MultiRegimeStay` with the villa and both plan names in the message.
  (test)
- Creating a second active plan for the same villa, currency and basis is
  rejected at the API with the guidance message. (test)
- Two periods in different plans of the same villa + currency cannot
  overlap (DB-level). (test)
- A stay in a partly priced year on unpriced dates projects with
  `is_projected=True`; a stay with one real night and one unpriced night
  uses fallback or fails. (test)
- Projection from a villa whose only prior periods sit in one year shifts
  by exactly one year; a two-year period set anchors on the later year
  only. (test)
- Carry-forward adds periods to the existing plan, is idempotent on the
  target year, and never creates a plan. (test)
- Loader: ~276 plans on the 24-Apr dump; zero cross-plan period
  collisions; night-parity invariant gap 0 with any residue explained;
  legacy-quote sample reproduces on the 37 overlap villas. (`reconcile_legacy`)
- Workbench: plan form has no date fields; coverage lane shows unpriced
  days across the visible year; carry-forward leaves the user on the same
  plan. (vitest)
- `04-pricing.md`, `decisions.md`, `CUTOVER.md` updated; SPEC-001 closed.

## Decisions taken / assumed (2026-09-11 design pass)

- **Adopt the regime-bucket cut** (SPEC-001 open decision 1), not the
  interim guardrail.
- **Legacy seasons merge to one plan per villa + currency**; season names
  demoted to plan notes. *Assumed, confirm.*
- **Two-regime stay is a loud error**, not a projection or a silent pick.
  *Assumed, confirm.*
- **Gap policy:** some real nights → real + fallback / fail; no real nights
  → project. *Assumed, confirm.*
- **Widened EXCLUDE is ungated by `is_active`.** *Assumed, confirm.*
- **One active plan per villa + currency + basis.** Added after the
  "yearly season habit" risk was raised; *assumed, confirm.*
- **Open, for Nick:** the GAP-035 decision text justifies per-plan basis
  with "a villa runs a GROSS public plan and a NET agent plan at once".
  Two concurrent same-currency plans on the same nights is exactly what U2
  forbids. No data does this today and the price path has no segment
  selector. If agent-vs-direct pricing is a real requirement, the partition
  becomes `(property, currency, segment)` with `segment` on the plan and
  the caller choosing it — a small extension, but it must be asked before
  U2 lands. Add to Q-028.

## Dependencies

- **SPEC-001** — the exploration this adopts; closes on landing.
- **BUG-028 §5** — the envelope parity item is superseded by U0/U6 (no
  envelope to widen); its "zero imported plans with a period outside their
  own window" acceptance line drops. BUG-028 §3 (currency resolution) feeds
  U0's currency grouping and should land first.
- **GAP-108** — the `RatePlan` reconcile constant moves; pin after U0.
- **BUG-029** — the two-run idempotency test covers the regrouped loader.
- **Q-022** — season tier lands on `RatePeriod`; U4 carries it. The regime
  model strengthens the period as the season-shaped object.
- **Q-018** — same carry-forward service; unchanged policy (base only).
- **GAP-035 / SMELL-021 ✅** — per-plan `price_basis` stays; see the open
  Nick question above.
- **GAP-014 ✅** — `pick_preferred_plan`'s recency rule is retired here.
- **SMELL-022 ✅** — the widened constraint lands as an `ExclusionConstraint`
  in `Meta`, no raw SQL.
