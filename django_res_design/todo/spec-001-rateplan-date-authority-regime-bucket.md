# SPEC-001 — Make `RatePeriod` the sole date authority; `RatePlan` becomes a dateless regime bucket

- **Severity:** 🔵 Speculative (design exploration — no committed decision; captures
  an investigation so the reasoning isn't lost. Demand-driven: adopt only if the
  drift bug below actually bites, or when the rate model is next opened.)
- **Source:** 2026-07-03 far-future-rates investigation (owner-feedback pass).
  Grew out of a question about how far-future enquiries are priced and turned
  into a rate-model critique.
- **Files (today's shape):**
  - `pricing/models/rate.py:52-53` — `RatePlan.effective_from` (bare `DateField`),
    `effective_to` (nullable); `:62` indexes them; `:59` orders by `-effective_from`.
  - `pricing/services/engine.py:531-543` (`_load_real_context`) — coverage gate keys
    on the plan **envelope** (`effective_from <= date_from AND (effective_to IS NULL
    OR >= date_to)`), *not* on period coverage.
  - `pricing/services/projection.py:157-166` (`find_anchor_plan`) + `:194-196`
    (`source_year = anchor.effective_from.year`) — projection anchor + year-delta
    derive from the plan scalar.
  - `pricing/migrations/0015_drop_ratecard_contract.py:25` —
    `rateperiod_no_overlap EXCLUDE USING gist (plan_id WITH =, daterange && )`
    (periods disjoint **per plan**).
  - `data_migration/loaders/pricing.py:322-323` — the envelope was **originally
    derived** as `MIN(FromDate)..MAX(ToDate)` over legacy `VillaSeasonDates`.

## Problem — the envelope-vs-period drift seam

Since GAP-056 the rate model is period-native: `Property → RatePlan → RatePeriod
(inclusive dates) → RateBand (party band)`. `RatePeriod` is meant to be the honest
date axis. Yet `RatePlan` still stores a `effective_from`/`effective_to` **envelope**,
and it's a bare, unconstrained `DateField` pair — nothing ties it to the plan's
periods. Two load-bearing reads key on that envelope instead of on the periods:

1. **Coverage** (`_load_real_context`): "does a real plan cover this stay?" is decided
   by the plan envelope. If the envelope is **wider** than the periods (a mid-year
   gap), the engine thinks it's covered and prices the gap at `fallback_nightly` or
   hard-fails — it does **not** project, so a *within-year* gap behaves differently
   from an *out-of-year* gap (which projects a guide). If the envelope is **narrower**
   than the periods, a real priced period can be masked. Both are drift the schema
   permits.
2. **Anchor + source year** (projection): `year_delta = target_year −
   anchor.effective_from.year`. If `effective_from` doesn't line up with where the
   periods actually sit, the whole-year projection shift lands a year off.

The envelope duplicates what the periods already know (`MIN(date_from) …
MAX(date_to)`) — and it *began life* as exactly that derivation at migration time
(`pricing.py:322-323`). It only became a free-floating stored field that can disagree
with reality. This is the root smell.

## Problem (adjacent) — coexisting same-currency plans have no invariant, only a recency guess

The schema permits **N `RatePlan` rows for the same `(property, currency)` overlapping
the same dates**. Nothing at the DB level forbids it: the only per-plan invariant is
`rateperiod_no_overlap` (`0015:25`, `plan_id WITH =`), which makes *periods* disjoint
**within a plan** but says nothing **across plans**. So two plans on the same villa,
same currency, can both claim to price the same night.

When they do, disambiguation is entirely **`pick_preferred_plan`**
(`currency.py:52-70`), a soft, ordering-dependent tiebreak, not a constraint:
`_load_real_context` (`engine.py:515-543`) gathers every plan whose *envelope* covers
the stay and picks `-effective_from, -pk` — **most recent `effective_from` wins, newest
`pk` breaks a same-day tie.** That is a silent guess: the loser is masked with no error,
and the winner flips if someone back-dates a plan or the rows reorder. The 18
overlapping legacy pairs the docstring cites are all *cross-currency*; the *same-currency*
overlap is unhandled by design because it wasn't supposed to happen — but nothing stops
it being authored in the workbench today.

### Should the constraint be "coexisting plans must differ by currency"?

This is the tempting fix, and it's **wrong on two counts**:

1. **Too strict on the wrong axis, too weak on the real one.** `price_basis`
   (GROSS/NET) is also plan-level (`SMELL-021`), so a currency-only uniqueness key
   would *permit* two same-currency plans that differ only by basis to overlap the same
   night — and the engine treats `price_basis` as a **per-stay singleton**
   (`engine.py:286-295`, the money authority): a stay drawing nights from a GROSS and a
   NET plan at once has no coherent basis. Overlap is ambiguous regardless of currency.
   Currency-difference neither prevents the ambiguity it should nor permits only what's
   safe.
2. **It doesn't match how selection actually works.** `pick_preferred_plan` resolves
   same-currency overlap by *recency*, i.e. it treats a same-currency overlap as legal
   and silently picks one. A "must differ by currency" constraint would make that path
   dead code and reject data the engine currently (mis)handles — a semantics change
   dressed as an integrity check.

**The correct invariant is the regime-era one this SPEC already proposes:** *at most one
active regime prices any `(property, currency, night)`.* That is **stricter** than
currency-difference (it also forbids two same-currency plans sharing a night) but scoped
to **active priced periods**, not plan envelopes — so it permits the *legitimate*
coexistence (same-currency plans whose periods don't overlap; a scheduled currency/basis
switch; explicitly-selected market segments where they exist) while forbidding the silent
guess. Implemented, it's the widened `(property_id, currency_id)` EXCLUDE in the
"Disjointness constraint widens" bullet below — which is why the two problems share a
fix.

Legitimate same-day coexistence that the invariant must **keep**: (a) different currency
(the EUR/GBP market split — the partition is `(property, currency)`, so these never
collide); (b) a scheduled future-dated switch where the new plan's *periods* start after
the old plan's end; (c) if/when the price path grows an explicit segment/market selector
(agent vs direct), plans chosen by the caller rather than auto-resolved. Today's price
path has **no** such selector — selection is fully automatic via `pick_preferred_plan` —
so today, same-currency same-night overlap is *only* ever the silent guess, never an
intended alternative.

## Recommended direction — cut the fields; `RatePlan` = regime bucket

Drop `effective_from`/`effective_to`. `RatePlan` becomes `property + currency +
price_basis + prices_by_occupancy + fallback_nightly + name + is_active + notes` — a
**pricing-regime bucket** whose temporal extent is *emergent* from its periods, never
stored. `RatePeriod.date_from/date_to` is the sole date authority.

Framing that keeps it coherent: **a plan is a regime era.** Currency and
`price_basis` are legitimately plan-level and *do* change over time (GBP→EUR,
GROSS→NET); a plan boundary is a regime boundary, which in practice is roughly annual
but isn't *defined* by the year. Historical accuracy is unaffected — old periods still
point at their old plan, which still carries its old currency/basis.

What changes:

- **Coverage → period-native.** `_load_real_context` selects candidate plans by
  currency/`is_active`, then asks "do active periods (with approved bands) price every
  night?" — the per-night resolver already answers this; an uncovered night with no
  `fallback_nightly` *is* the projection trigger. **This incidentally fixes the
  mid-year-gap inconsistency** — within-year and out-of-year gaps become the same
  event, so you make one deliberate gap policy instead of two accidental ones.
- **Anchor + source-year → period-derived.** Anchor = the most recent priced
  period-set before the target year; `source_year` = that set's year. The synthetic
  `proj_plan` envelope in `projection.py` and the `carryover.materialise` envelope
  simply stop being written.
- **Disjointness constraint widens** — this is the one genuinely invasive change.
  Today periods are disjoint *per plan* (`plan_id WITH =`); the envelope was the
  implicit tiebreak when two same-(property, currency) plans overlapped in date. Cut
  the envelope and that tiebreak is gone, so the invariant must become **"at most one
  regime prices any (property, currency, night)"** — the EXCLUDE partition moves to
  `(property_id, currency_id)`. Postgres can only reference same-table columns, so
  this **forces `property_id` + `currency_id` to be denormalized onto `RatePeriod`**
  (kept in sync). The regime-era model makes this invariant true anyway (you don't run
  two GBP regimes at once), so it encodes a real rule.
- **Ordering / currency-recency:** `Meta.ordering = ["-effective_from"]` and
  `pick_preferred_plan`'s recency tiebreak (GAP-014) need a period-derived "most
  recent" instead of the scalar.

Costs / caveats:

- **Empty plans lose their year.** An empty or half-priced plan ("the 2028 GBP plan I
  just created") has *no* temporal identity until a period exists on it. This is the
  one genuine new limitation and it has a workbench consequence (how do you scope a
  view to "2028" before a 2028 period exists?). Needs a UX answer.
- **Migration is the *easiest* of the options** — periods already hold their dates
  verbatim; you drop the derived envelope, no date rewriting. But land the engine /
  projection re-derivation in the *same* change or quoting breaks mid-deploy. Audit
  first: any existing plan where `envelope ≠ period-union` is a latent inconsistency
  to reconcile before dropping (the drift, made visible).
- **FE/serializer blast radius unknown** — `RatePlanDetailSerializer` exposes the two
  fields and the workbench scopes a view by year via the envelope. Grep `frontend/`
  for `effective_from` before committing to scope.

**Cheaper interim option (if the full cut isn't taken):** bind the envelope to the
periods — make `effective_from`/`effective_to` a derived/computed value, or add a
constraint that the envelope must contain the period union. That removes the *drift
bug class* without the constraint-migration, and leaves the fields as a cheap indexed
query surface. Lower reward, much lower cost; a reasonable "do this now, cut later"
step.

## Considered and REJECTED — explicit `year: int` on `RatePlan`

An alternative was explored and **rejected on 2026-07-03**: replace the date fields
with an integer `year`, constrain each `RatePeriod` to fall within its plan's year
(splitting a cross-year "winter" season into two periods on two plans), and make
extras/discounts/inclusions optionally plan-scoped so carryover carries them forward
explicitly.

It has real attractions — the **crispest plan identity** (no envelope, no drift),
the **cleanest carryover** (N → N+1), empty plans keep their year, and explicit
plan-scoped offer-item carry that would solve the season-linkage drift noted below.

It was rejected because it **introduces the first scenario where a single stay spans
two pricing regimes**, which the engine was explicitly designed *not* to have:

- **Cross-year *stays* break, not just seasons.** A New Year stay (e.g. 28 Dec →
  4 Jan) — often the single highest-value week for a luxury villa — would draw nights
  from two plans/years, so no single plan covers it and `_load_real_context` would
  wrongly fall through to projection.
- **Engine assessment (`engine.py:136-345`):** the per-night loop is period-driven
  and *would* merge cleanly if you concatenated two plans' periods/bands; min/max-
  nights disagreement is **already** handled (strictest-wins across touched periods,
  `:219-230`). BUT `currency` (`:141,237`), `price_basis` (`:286-295`, THE money
  authority — commission/tax derived once on the aggregate `base`), and
  `fallback_nightly` (`:182-188`) are **per-stay singletons**. A stay straddling a
  GROSS and a NET plan, or a currency switch landing on the straddle, has no coherent
  single basis/currency and is **unpriceable without segment-and-sum** (price each
  year under its own regime, then combine) — a structurally different engine.
- **Migration is harder than the recommended direction:** legacy seasons are *not*
  year-partitioned (multi-year `VillaSeasonRate` rows with their own dates), so the
  loader would have to shred each season into year-plans and split boundary-crossing
  rows at Jan 1, and the row-count reconcile becomes fuzzier (1 legacy row → 1 *or 2*
  periods).

Net: the year model optimizes carryover/identity at the cost of a permanent,
runtime multi-regime-stay problem on the most valuable booking of the year. The
recommended (cut-dates) model and today's model both keep **one stay → one regime**
even across a year boundary. Not worth it.

## Related findings carried from the same investigation (context, not scope)

- **Offer-item scoping is correct but has a drift tension.** `Discount`, `Extra`, and
  inclusions (`PropertyService`) are all **property-scoped with their own date
  windows**, not keyed off the plan — right, because they describe the villa's
  offering, not a pricing regime, and it keeps projection/carryover from having to
  clone them. Tension: because their windows are *absolute*, a "peak-season" extra or
  inclusion **won't follow a season that shifts** on carryover — it must be re-dated
  by hand. (Legacy scoped all three on the seasonal rate card / season header; the
  rebuild's lift-to-property is a deliberate modernization — see Q-022.)
- **Cutover parity gap (separate ticket-worthy):** legacy **extras** (`VillaSeasonRate
  IsExTra=1`) and **all legacy discount columns** (`IsDiscount`/`DiscountRate`/…) are
  **not ported** — the base-rate loader filters `IsExTra <> 1` and never reads the
  discount columns, so the new `Extra`/`Discount` tables start **empty** for migrated
  villas. Inclusions *are* ported (GAP-037). Confirm whether the drop is intentional
  or an un-ported surface; if intentional, record it in `CUTOVER.md` expected-losses.
- **Workbench carry-forward affordance** already filed as **GAP-069** (the
  `…:carry-forward` endpoint exists but has no SPA caller).

## Open decisions

1. Adopt the regime-bucket cut, take the cheap envelope-follows-periods guardrail, or
   leave as-is (demand-driven — has the drift actually bitten?).
2. If cutting: what's the gap policy once coverage is period-native (project /
   fallback / fail for a within-year gap)?
3. How does the workbench scope a plan/year when an empty plan has no dates?
4. Is the offer-item season-linkage drift worth addressing (and does that reopen any
   argument for plan-scoped offer-items — the one good idea the rejected year model
   had)?
5. Same-currency plan overlap (adjacent problem): confirm the regime invariant "at most
   one active regime per `(property, currency, night)`" is the intended rule — i.e. we
   reject the "coexist iff different currency" constraint — and decide whether a cheap
   interim guard is worth it (a validation-layer check rejecting a new plan/period that
   overlaps an existing same-`(property, currency)` priced night) ahead of the full
   widened-EXCLUDE cut, since `pick_preferred_plan`'s silent guess is a live foot-gun in
   the workbench now.

## Acceptance (for the exploration, not a build)

- Decision recorded here (adopt / guardrail-only / defer) with a date.
- If **adopt**, spawn build tickets: (a) `RatePeriod` `property_id`/`currency_id`
  denormalization + widened `(property, currency)` EXCLUDE; (b) engine coverage +
  projection anchor re-derived from periods, with the chosen gap policy; (c) FE /
  serializer audit + empty-plan scoping UX; (d) drop the fields + pre-drop drift
  reconcile.
- If **guardrail-only**, one ticket: bind the envelope to the period union
  (derived value or containment constraint).

## Dependencies / related

- **Q-022** (seasons defined by rates) — closely related; this is the structural
  counterpart to that question.
- **Q-018** (rate reduction vs carryover) — same carryover service; shares the
  projection/materialise path.
- **SMELL-021** (`PriceBasis` two sources) / **SMELL-022** (EXCLUDE constraints raw
  SQL only) — the constraint work here should land alongside porting the EXCLUDE to
  `ExclusionConstraint`.
- **BUG-016** (rate-grid disjointness reimplemented by 4 producers) — the widened
  constraint + period-native coverage reduce the surface this bug lives on.
- **GAP-069** (workbench carry-forward affordance).
