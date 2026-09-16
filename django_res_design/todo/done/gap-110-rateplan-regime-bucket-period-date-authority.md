# GAP-110 — `RatePlan` becomes a dateless regime bucket; `RatePeriod` is the sole date authority; legacy seasons load as one plan per villa + currency

> **✅ RESOLVED (2026-09-14)** — shipped on `feat/gap-110`; fast-forwarded into
> local `main` (unpushed) at close-out. 8 code units + this close-out, expand →
> migrate → contract as planned:
> f55486df U0a `RatePlanLoader` groups seasons into one plan per (villa,
> resolved currency); b936f09a U0b `RateBandLoader` builds periods on the
> regime plan + reconcile villa-level plan check and night-parity section;
> 4436e7b0 U1 `RatePeriod.property/currency` stamped from the plan (mig
> 0008/0009), plan property/currency locked once periods exist; 6d8cc9d1 U2a
> `rateperiod_no_overlap` on `(property, currency)` (mig 0010) + `RatePlan:duplicate`
> removed; e7e01ebe U3 engine selects periods first, then infers the plan,
> `MultiRegimeStay`; ad0c86f8 U4 anchor on a period year, carry-forward writes
> into the regime plan, `rateplan_one_active_per_regime` (mig 0011); 463b220e
> U5a + U6a API/seeding/factories drop the envelope, mig 0012 removes
> `effective_from/effective_to` + the orphaned `idempotency_key`, ordering
> `(property, pk)`, `PropertyFinance.season` dropped (properties/0008);
> b3b829bf U5b the rate workbench follows the date-less plan.
>
> **What exists now.** A `RatePlan` is a date-less regime bucket — at most one
> *active* plan per `(property, currency, price_basis)`; retired plans may pile
> up and their periods still own their dates. `RatePeriod` carries denormalised
> `property` + `currency` (stamped from the plan on save, never from input) and
> `rateperiod_no_overlap` partitions on them, ungated by `is_active`. The
> engine fetches the active periods (of active plans) touching the stay and
> infers the plan: none → projection; one → that plan; two in one currency →
> `MultiRegimeStay` (a `NoRateAvailable` subclass, same `code`, detail names the
> villa and both plans). Projection anchors on a **period** year
> (`find_anchor(property, currency, target_year) → Anchor(plan, source_year)`)
> and projects only that year's periods; carry-forward writes into the anchor
> plan (never creates one), is idempotent on the target year, refuses a year
> owned only by withdrawn rows as 409 `RegimeConflict`, clips around
> neighbouring-year rows, and logs `pricing.carryover.materialised` as its
> provenance; the admin action year is `next_target_year` (latest live period
> + 1). Serializer pre-checks give 400s with guidance (cross-plan overlap keyed
> `date_from` naming the other plan; second active plan → non-field error naming
> the occupant; currency change on a plan with periods); a raced constraint hit
> is a 409 `regime_conflict`. The loader mints one plan per (villa, resolved
> currency), `legacy_id="villa:<VillaId>:<CODE>"`, season names → `notes`,
> overlaps resolved per regime. The workbench plan form has no dates, the
> coverage lane shows unpriced days across the visible year, the picker reads
> `EUR · Gross` (+ inactive marker), and carry-forward follows the returned plan.
>
> **Deviations from the ticket / plan, all deliberate (review findings):**
> (a) the pricing context carries only the chosen plan's periods *touching* the
> stay, not all of them — plans are multi-year buckets and `stay_length_bounds`
> must not see another year; `load_context()` returns a context only when
> those periods cover every night (its sub-stay reuse contract), while
> `quote()` still fallback-fills a partly covered stay. (b) With `currency=None`
> the currency whose periods cover the **most** nights wins, then the settings
> currency, then lowest plan pk (the ticket said "settings currency, then pk").
> (c) `resolve_property_currency` = covering-today plan, else latest elapsed
> period's plan, else settings, **else the earliest upcoming period's plan**,
> else EUR. (d) The changeover shift runs before plan selection, so the
> *shifted* nights pick the regime. (e) `PoaRate(NoRateAvailable)` was added so
> stay options can branch on type. (f) `find_anchor` needs no approved band
> (keeps the fallback-only projection); the projected context carries the real
> regime plan, no synthetic envelope copy. (g) `materialise` refuses — rather
> than clips around — a target year owned only by withdrawn rows; `map_range`
> keeps a mapped start inside its target year. (h) No plan-level provenance
> note (no plan is created); the log event is the record. (i) The FE keeps
> following the carry-forward response id: the carry target is resolved by
> (property, currency), so from a periodless EUR·Net plan the carry lands on —
> and returns — the EUR·Gross plan; "same plan" is only the common case. (j)
> A periodless plan with `fallback_nightly` no longer prices (gap policy: no
> real nights → project). (k) `RatePlan.idempotency_key` went with `duplicate`;
> migration 0011 first retires pre-regroup season-keyed loader plans. (l) U6a
> (mig 0012) was folded into U5a — the API could not stop writing a NOT NULL
> column without a throwaway default. Q-022's tier is not carried (no field
> exists). Manual `/demo-worktree` browser check was not run.
>
> **Open follow-ups — ✅ ALL THREE CLOSED by GAP-108's ResProd dry run
> (2026-09-16), which had the `LEGACY_DATABASE_URL` this ticket lacked. They
> were recorded in `CUTOVER.md` §5 items 3–5; see `DRYRUN_LOG.md` run 5:**
> - ✅ Loader / **reconcile expected-gap calibration**. The villa-level
>   `RatePlan` check's placeholder is gone; the `VillaSeasonRate` check needed
>   its legacy SQL **replaced**, not recalibrated — the old query counted a
>   universe the loader never reads. Legacy side 7 095, gap **462** = 495
>   shadowed bands − 8 occupancy-fallback − 25 `#seg`, each itemised on the
>   `_Check`. `test_documented_expected_gaps_are_encoded` now pins the whole
>   `_CHECKS` gap map as one dict, so none of this can drift silently again.
> - ✅ **Night-parity invariant** — gap 0 on ResProd. No residue to itemise.
> - ✅ **Legacy-quote sample** (`.claude-tmp/gap110-quote-sample.py`, now
>   committed): 558 lines sampled on the overlap villas, **526 exact**, 0
>   changeover-shifted, and every one of the 32 non-exact lines explained:
>   - **28 `PartyOutOfRange`** — the party exceeds the top of the villa's
>     occupancy grid (= `Property` capacity; there are no holes *inside* any
>     grid). This is the known departure in `09-departures.md` #2 — legacy
>     ignores `PartySize` — surfacing where staff quoted over capacity, e.g.
>     villa 51 quoted for 16 guests against a cap of 6. Re-priced at the grid
>     top they reproduce legacy on 10 of 11 villa/quote cases.
>   - **1 `NoRateAvailable`** — villa 418 quote 4280, night 2027-01-02
>     uncovered at a USD→EUR card switch; legacy filled it from
>     `SettingNightlyPrice` (the SMELL-007 / GAP-008 `fallback_nightly` path).
>   - **3 band-drift mismatches** — the occupancy band was edited *after* the
>     quote was issued. The villa 92 / quote 4642 residue (legacy 12 750 vs
>     engine 17 500) that survives re-pricing at the grid top is the same
>     class, not a fourth case.
>   **No engine or loader bug, and nothing quotes a wrong price** — every
>   non-exact case refuses rather than inventing a number. So the ticket's
>   unticked "one-plan stays quote identically before and after" line is now
>   evidenced against the old engine, not just against the projection.
>
> **Deferred (out of scope, own tickets):** BUG-028 §3 currency-resolution fix
> (loader uses today's chain); `segment` on `RatePlan` for agent-vs-direct
> pricing (Q-028 item 5, still open for the owner); Q-022 season tier on
> `RatePeriod`; a distinct API error code for `MultiRegimeStay` + FE branch;
> `IntegrityError` → DRF mapping in the global exception handler;
> trigger-based audit capture for bulk writes.

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
  *As landed (e7e01ebe):* with `currency=None` the engine first ranks the
  currencies touching the stay by nights covered (most wins), then the
  settings currency, then lowest pk; `resolve_property_currency` adds
  "else the property's settings currency, else the plan owning the earliest
  upcoming period, else EUR" after the two steps above.
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

- ⬜ **Not proven as written.** Cross-producer equivalence tests pass unchanged
  for every stay that has real coverage under one plan: quotes are identical
  before and after. — `test_cross_producer_equivalence.py` was *edited* on the
  branch (fixtures moved to the regime shape) and it pins **projected ==
  materialised** parity, not pre-/post-GAP-110 quote identity; there is no
  dedicated before/after regression guard for one-plan stays. What covers the
  one-plan path is the U3 engine suite: `pricing/tests/test_engine.py` (e.g.
  `test_quote_happy_path_single_card_no_extras`, the fallback/reduction/
  breakdown cases — unchanged assertions on a single-plan fixture) and
  `pricing/tests/test_engine_regime.py`
  (`test_context_carries_only_the_plans_periods_touching_the_stay`,
  `test_plan_currency_drifted_from_its_periods_still_quotes`).
- ✅ A stay checking out on the last day of a priced period prices. (test —
  `test_engine_regime.py::test_new_years_day_checkout_prices_on_the_period_ending_31_dec`)
- ✅ A stay touching periods of two plans in one currency raises
  `MultiRegimeStay` with the villa and both plan names in the message.
  (test — `test_gross_and_net_plans_touching_one_stay_raise_multi_regime_stay`,
  `test_multi_regime_stay_is_a_409_no_rate_available`)
- ✅ Creating a second active plan for the same villa, currency and basis is
  rejected at the API with the guidance message. (test —
  `test_api_rate_plans.py::test_create_plan_into_an_occupied_regime_rejected_with_guidance`,
  `test_rate_plan_regime.py`)
- ✅ Two periods in different plans of the same villa + currency cannot
  overlap (DB-level). (test —
  `test_rate_period.py::test_rateperiod_overlap_blocked_across_plans_in_one_regime`)
- ✅ A stay in a partly priced year on unpriced dates projects with
  `is_projected=True`; a stay with one real night and one unpriced night
  uses fallback or fails. (test —
  `test_unpriced_dates_of_a_partly_priced_year_project_from_the_prior_year`,
  `test_engine.py::test_fallback_nightly_fills_gap_night` /
  `test_gap_night_without_fallback_still_raises`)
- ✅ Projection from a villa whose only prior periods sit in one year shifts
  by exactly one year; a two-year period set anchors on the later year
  only. (test — `test_projection.py::test_find_anchor_returns_latest_period_year_before_target`,
  `test_project_carries_only_the_source_year_periods`)
- ✅ Carry-forward adds periods to the existing plan, is idempotent on the
  target year, and never creates a plan. (test —
  `test_carryover.py::test_materialise_writes_real_rows_for_target_year`
  asserts one plan in the regime, `test_materialise_is_idempotent*`,
  `test_api_rate_plans.py::test_carry_forward_creates_editable_plan_for_future_year`)
- ✅ **CLOSED by GAP-108's ResProd dry run, 2026-09-16** (this ticket had no
  `LEGACY_DATABASE_URL`): zero cross-plan period collisions; night-parity gap
  **0**, no residue; the legacy-quote sample runs clean on the overlap villas
  — 558 lines, 526 exact, 32 explained, 0 quoting a wrong price. Every
  `expected_gap` placeholder is now a pinned constant with an itemised
  zero-residual derivation, and the `VillaSeasonRate` check's legacy SQL was
  replaced rather than recalibrated. Detail in the banner at the top of this
  ticket; `CUTOVER.md` §5 items 3–5 are discharged.
- ✅ Workbench: plan form has no date fields; coverage lane shows unpriced
  days across the visible year; carry-forward leaves the user on the same
  plan. (vitest — `RatePlanFormDialog.test.tsx` "… and no dates",
  `coverageGaps.test.ts` "surrounds a mid-year period with a leading and a
  trailing gap", `RateWorkbenchPage.test.tsx` "carries earlier rates forward
  into the SAME plan …" — *and* "follows the response plan when the carry
  lands on the other-basis plan in the same currency", the one deliberate
  exception, deviation (i) above.) Manual browser check not run.
- ✅ `04-pricing.md`, `decisions.md`, `CUTOVER.md` updated; SPEC-001 closed
  (this close-out, 2026-09-14).

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
