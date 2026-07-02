> **✅ RESOLVED (2026-07-01)** — Shipped on local `main` (unpushed) via
> `feat/gap-056` in 9 units + a `main` merge. The rate tree is now honestly
> two-level: `Property → RatePlan → RatePeriod → RateRule`, `RateCard` **dropped**.
> A `RatePeriod` owns an **inclusive** date window (`date_from <= date_to`,
> single-day allowed) + nullable `min_nights`/`max_nights` + `name`/`is_active`;
> a `RateRule` is a party band (`min_party`/`max_party`, `nightly`/`weekly`,
> `is_poa`, `is_approved`) hanging off a non-null `period` FK — no dates, no card.
> Two Postgres `btree_gist` EXCLUDEs enforce the honest grid: periods
> date-disjoint per plan (`rateperiod_no_overlap`), bands party-disjoint per
> period (`raterule_bands_no_overlap`). Built expand→migrate→contract so every
> commit stayed green.
>
> **Commits:** U1 segmentation util `f39b84f`; U2 RatePeriod level + repoint
> (expand) `72e89b1`; U3 engine period-native + relocate min/max-nights `098e287`
> (+review `6e5975d`); U4 carryover native periods `54900cc`; U5 loader disjoint
> period axis `b0b302a`; U6 API/serializers/signals/tasks/audit `27f11f5`
> `6ce7495` `dbe3aba` (+review `e8875de`); U7 Discount property-only `5914f4e`;
> U8 period-native frontend `d3b14fb` (+review `5d66044`); U9 contract — drop
> RateCard, add EXCLUDEs `26076f5`.
>
> **Corrections to the ticket body (as-built differs — see plan
> `~/.claude/plans/cryptic-greeting-thacker.md`):**
> 1. **`PropertySettings.max_nights_rental` was NOT added.** Max is period-only
>    (`RatePeriod.max_nights = NULL` ⇒ "no max"); a villa-wide max default (and
>    the matching `GroupSettings` field + `_INHERITABLE_FIELDS` entry) was judged
>    not worth it (KISS; legacy has no max concept). The min default **does**
>    reuse the existing `PropertySettings.min_nights_rental`. Body rows that say
>    "add `max_nights_rental` (new)" are superseded.
> 2. **Multi-period min-nights is NOT uniformly "strictest wins".** It splits by
>    caller: the per-stay `quote()` guard is **strictest-wins**
>    (`min = max(touched mins)`) — the loud guard; the stay-agnostic
>    `stay_length_bounds` search pre-filter is **loosest-wins**
>    (`min = min(all mins)`, no max unless every period caps) so a villa with a
>    7-night peak + 3-night off-peak still offers the 3-night off-peak stays.
> 3. **`period_backfill.py` did NOT already exist** ("reused from BUG-014" was
>    wrong — only `segmentation.py` predated this). It was built in U2 as the
>    migration-0013 backfill (historical-model glue).
> 4. **Party-gap base band** (every active period covers `1..max_occupancy`, POA
>    an explicit band) — ticket was right; implemented as a `RatePeriodSerializer`
>    activation-gated coverage check + read-only `coverage_gaps` (U6) with the
>    matrix-editor warning (U8).
>
> **Deferred (out of scope):** villa-level `max_nights`; `/seasons`→`/plans`
> route rename (cosmetic debt accepted); BUG-009 owner-economics / finance
> rewrite; sibling BUG-002/BUG-003. **Known/accepted:** the U2 backfill stamps
> `RatePeriod.is_active=True` regardless of the dropped card's `is_active` — zero
> prod impact (cards vestigial, none inactive per the dump parse). **Tests:**
> 2286 backend passed (2 pre-existing unrelated `accounts` migration-isolation
> errors) + 1477 frontend green; mypy/ruff/format/tsc/eslint/prettier clean;
> `0013→0015` migrate clean on a fresh DB.

---

# GAP-056 — Restructure the rate model: drop `RateCard`; `Property → RatePlan → RatePeriod → RateRule` (per-period min/max nights; first-class occupancy)

- **Severity:** 🟢 Gap / architectural restructure — the current four-level rate
  tree (`RatePlan → RateCard → RateRule`) has two habitually-degenerate levels,
  no honest date×occupancy grid, and no per-period stay-length control. Nothing
  is *wrong-money-out* today, but the shape blocks a correct occupancy-pricing
  UX and carries abstraction (card precedence) that neither legacy nor prod data
  ever used.
- **Source:** 2026-07-01 rate-model investigation (legacy .NET schema + a full
  parse of the 36 MB prod SQL-Server dump). Supersedes and subsumes
  [BUG-014](bug-014-raterule-flattened-period-occupancy-hierarchy.md) (the
  period→occupancy-band hierarchy is the core of this larger change).
- **Files touched (best-guess):**
  - `django_res/pricing/models/rate.py` — the model tree itself
  - `django_res/pricing/services/engine.py` (`_load_real_context`, `quote`,
    `covering_bands`, `_rules_cover_all_nights`), `services/rates.py`
    (`pick_rule_for_night`), `services/projection.py`, `services/carryover.py`
  - `django_res/pricing/serializers/rate.py`, `views/rate.py`, `urls`
  - `django_res/data_migration/loaders/pricing.py` (+ `reconcile_legacy`,
    `CUTOVER.md`)
  - `django_res/pricing/services/segmentation.py` + `period_backfill.py`
    (already built for BUG-014 — reused here)
  - `frontend/src/features/rate-workbench/*`, `frontend/src/features/properties/{schemas,api}.ts`
  - `django_res/properties/models/property.py` (new villa-level pricing fields)

---

## Why now — the investigation

BUG-014 set out to insert a `RatePeriod` between `RateCard` and `RateRule` to
kill *ragged* occupancy bands. Scoping that fix surfaced a bigger structural
question — **how deep does the rate tree actually need to be?** — which we
answered against the real legacy schema and prod data.

### Legacy data model (the source of truth we're reproducing)

Legacy used **four** tables, per villa:

```
VillaSeason ............... a NAMED label, per villa — NO dates of its own
  └──< VillaSeasonDates .... the season's calendar footprint = a UNION of windows
  └──< VillaSeasonRate .... a PRICED row with its OWN [FromDate,ToDate]  (≈ a "period")
         • TotalNight  = span length (NOT a min-stay — see findings)
         • PriceType (net/gross), IsPoa, IsOccupationPrice, IsExTra
         • NightlyPrice / WeeklyPrice   (used when IsOccupationPrice = FALSE)
         • PartySize (dead column, always 0)
         └──< VillaOccupencyPrice ... occupancy BANDS — NO dates of their own
                • OccupencyFrom / OccupencyTo / OccupencyPrice
```

Two structural facts fall out of "occupancy children carry no dates":

1. **Within a rate**, every occupancy band shares that rate's dates *by
   construction* — ragged bands inside one rate are impossible.
2. **Across rates in a season**, dates are free-form and may overlap. Legacy is
   *"aligned within a rate, free-form across rates."*

### What prod data actually contains — `VillaSeasonRate` row census

A full paren/quote-aware parse of `ResSystem/Database/DbScript.sql` (UTF-16LE;
parser at `scratchpad/parse_rates.py`, 0 rows mis-tokenised) breaks down as:

```
5,138  raw VillaSeasonRate INSERTs
−1,333  soft-deleted (DeletedAt IS NOT NULL)      ← the table soft-deletes
 3,805  live (DeletedAt IS NULL)
  −137  live extras (IsExTra = 1)                 ← extras cohabit the rate table
 3,668  live TRUE rates (DeletedAt NULL, IsExTra=0)  across 279 villas
```

The loader **must** filter `DeletedAt IS NULL` and split `IsExTra=1`
(extras route via `OldId_ExtraRate`, already handled in `pricing.py`). The
"3,773" figure in earlier drafts sat between the 3,805-live and 3,668-true-rate
counts and is superseded by this census.

| Capability | Real usage (verified) | Conclusion |
|---|---|---|
| **`TotalNight` as min-stay** | `TotalNight == (ToDate−FromDate).days` for **3,668 / 3,668** live rates — **0 mismatches** | It is a *derived span length*, not a minimum-stay. |
| **Occupancy banding** | **0** rows with `IsOccupationPrice=1` **anywhere** (live or deleted); 11 `VillaOccupencyPrice` rows across 4 parents (flag off) | Vestigial — a *broken* feature, not an unwanted one (see below). |
| **`PartySize`** | 3,612 zero; 56 junk (13 distinct incl. `120`) | Dead column; occupancy was never done this way. |
| **Named seasons** | 664 `VillaSeasonDates`; median **2 seasons/villa**, mostly 1 window each | Light grouping; multi-window barely used. |
| **Raggedness** | ~9–10 groups with genuine interior date overlap | Rare edge case, mostly a whole-year fallback band under weekly rows. |
| **Per-period min-nights** | *No such column exists* on rate/season tables | Not modelled at the period level at all. |
| **Per-villa min-nights** | `VillaMaster.SettingMinNightsRental` = **0.00 for all ~423 villas** | Override column completely unused. |
| **Global min-nights** | `VillaConfigPropertyDefault.MinimumNightsRental` = **7.00** (single row) | The single value that actually applied to everyone. |
| **Max-nights** | *No column anywhere* | Legacy has no max-stay concept. |
| **Currency** | live-rate `CurrencyId`: `EUR(3)=2354, NULL=993, GBP(1)=282, id0=20, id6=19`; **23 villas** with >1 distinct non-null currency | Multi-currency is real (**23**, not 19) **but 27% of live rates carry NO currency** — loader needs a NULL→default rule (see below). |
| **`IsPOA`** | 26 live rates | POA is used, rarely. |
| **Typical shape** | median **6 rates per (villa, season)**, ~one row/week | Contiguous **weekly-tiled flat periods**. |

**NULL-currency handling (new, load-bearing).** 993 of 3,668 live rates have
`CurrencyId = NULL`, and ids `0` and `6` also appear (not just GBP/EUR). Since
the engine selects a `RatePlan` **by currency**, every migrated rate must land
under a plan with a concrete currency. **Rule:** resolve a rate's currency as
`CurrencyId if not null/0 else the villa's dominant non-null rate currency else
VillaConfigPropertyDefault.CurrencyId else GBP`. Document the resolution counts
in `reconcile_legacy`.

**Critical semantic gotcha:** legacy `ToDate` is **checkout-exclusive**; our
engine matches dates **inclusively** (`date_from <= night <= date_to`). Adjacent
weekly tiles (`5/6–5/13` then `5/13–5/20`) *touch* but do not overlap — the
naive inclusive-overlap read over-counted "ragged" groups ~50×. The
legacy→new conversion must **universally** map `[From, To]` → inclusive
`[From, To−1]` **before** segmentation (`TotalNight == span` confirms every row
is a checkout-exclusive span, so an isolated non-adjacent period over-counts its
last night by one unless trimmed). ⚠️ The current loader
(`resolve_rate_rule_overlaps`) trims **only conditionally on detected
adjacency** — this must change to a universal per-row `−1` trim, and
`reconcile_legacy` expected gaps recalibrated accordingly.

**Occupancy is load-bearing, not optional.** Its ~0 legacy uptake reflects the
broken data structure (occupancy children hung off free-form overlapping rates,
no grid, easy to mis-edit, easy to leave party gaps unpriced), *not* lack of
demand. Making occupancy pricing actually work is a primary goal here.

### The two degenerate levels

- **`RateCard` — cut it.** Its only unique job is `sort_order` *precedence*
  (stacking overlay cards). Legacy had **no precedence concept** (the loader
  literally trims overlapping rows because legacy couldn't express them); no prod
  villa uses >1 card; promos/discounts already live in the separate `Discount`
  model. It is a speculative abstraction. `min_nights/max_nights` are its only
  other payload and they do not belong on a precedence layer — but **note they
  are not inert metadata**: the engine actively enforces them today
  (`_validate_card_against_stay` → `MinNightsNotMet`, `engine.py:531-539`;
  cross-card aggregation `478-484`; surfaced in breakdown `324-325`; tested at
  `test_engine.py:894+`). Cutting the card therefore **relocates live, tested
  stay-length logic** onto the period — it is *not* a greenfield add. See
  "Min/max nights" under decisions for the new resolution semantics.
- **`RatePlan` — KEEP (confirmed load-bearing).** It carries `currency`,
  `price_basis`, a validity window, and `fallback_nightly`. Its multiplicity is
  real on two counts:
  - **Currency** — prod has **23 villas priced in ≥2 currencies** (chiefly GBP+EUR,
    but ids `0` and `6` also appear), with *hand-set per-currency prices* (not FX
    conversions). The engine treats currency as a **plan-level selector**
    (`engine._load_real_context` → `covering.filter(currency=currency).first()`,
    `services/engine.py:512`; when currency is `None` it prices in the plan's own
    currency with **no** conversion, `engine.py:135-137`). Collapsing currency onto
    `Property` would break those villas. (See the NULL-currency resolution rule
    above — 27% of live rates need a default assigned at load time.)
  - **Year-versioning** — `carryover.materialise` creates one plan per
    `(currency, year)` and projection anchors on it.

  So `RatePlan` stays as the per-`(currency [, year])` **rate sheet**. This is the
  **thin-sheet** shape (option B): keep the plan, drop only the card.

### Vocabulary debt (surfaced, must be resolved)

The REST surface exposes `RatePlan` as **"Season"** (`/properties/{id}/seasons`,
`/seasons/{id}` back onto `RatePlan`), and the loader maps `VillaSeason →
RatePlan` 1:1. But the legacy season's *defining trait* — a **named date window**
— is exactly what `RatePeriod` now owns. Post-restructure, "Season" (the API
noun) is a misnomer: the date concept lives on the period. Renaming the API
noun (or moving the name onto the period) is in scope.

---

## Decisions already taken

- **Drop `RateCard` (only).** No precedence layer; min-stay granularity is served
  by the villa default or the period override, never the card. `RatePlan` stays —
  **thin-sheet (option B)**, confirmed by the multi-currency evidence above.
- **Occupancy bands are first-class.** A `RatePeriod` owns a complete party-band
  set; the date×occupancy **grid** is the natural shape, not a rare toggle.
- **Per-period min/max nights** — `min_nights` / `max_nights` become **nullable
  overrides on `RatePeriod`**; a `NULL` inherits the villa default. The
  *per-period* granularity is the new capability (seasonal min-stay: 7-night peak
  / 3-night off-peak), but enforcement itself already exists (see the RateCard
  note above) and is being **relocated**, so engine parity tests are mandatory.
  - **Villa default = reuse the existing `PropertySettings.min_nights_rental`**
    (`properties/models/settings.py:68`, nullable) — do **not** add a new
    `Property.default_min_nights` (KISS). ⚠️ This field is **not currently read by
    the engine** (min-stay is card-only today); wiring the engine to fall back to
    it is part of this work. There is **no** property-level `max_nights` — add
    `PropertySettings.max_nights_rental` (nullable) if a villa-wide max default is
    wanted; otherwise `RatePeriod.max_nights=NULL` simply means "no max".
  - **Multi-period stay → strictest wins.** A stay spanning several disjoint
    periods with different overrides resolves to **`min_nights = max(...)`** and
    **`max_nights = min(non-null ...)`** across every period the stay touches
    (replacing the old winning-card single value). Prevents a short booking from
    clipping a peak period. New engine test required.
- **Party-gap coverage → require a base band.** Every `RatePeriod` **must** carry
  a catch-all band covering `1..max_occupancy` (editor enforces at save; a DB/
  serializer check backs it). Uncovered guest counts are impossible; POA is an
  explicit band, never a silent gap. (The migration already synthesises
  base-weekly fallbacks — see BUG-013 — which satisfies this by construction.)
- **Optional period name.** Add a **nullable `name`** on `RatePeriod` for operator
  labels ("Peak", "Christmas") — a *label only*, no grouping semantics, no
  named-season layer (prod data doesn't warrant one; median ~2 seasons/villa).
- **Keep `/seasons` = `RatePlan`.** Do not rename the API noun. The plan stays
  "Season" in the REST surface even though the period now owns dates — accepted
  cosmetic debt in exchange for zero API/FE churn.

## Target model (option B — thin sheet)

```
Property (villa)  +  PropertySettings { min_nights_rental?, max_nights_rental? (new) }  ← villa-wide defaults
      │  1
      │  N        multiple ONLY across currency / year (23 villas: GBP+EUR & others)
   RatePlan   "rate sheet"  { currency, price_basis, fallback_nightly, effective_from/to }
      │  1
      │  N        periods on a plan are DISJOINT in date (EXCLUDE)
   RatePeriod   [ date_from .. date_to ]  (inclusive; single-day allowed)
      { name?, min_nights?, max_nights? }   ← nullable override of the villa default; name is a label
      │  1
      │  N        bands in a period are DISJOINT in party (EXCLUDE); MUST cover 1..max
   RateRule  (the "band")
      { min_party, max_party, nightly? | weekly? | is_poa, is_approved, is_locked }
```

- **`RateCard` is gone**; `RatePeriod` hangs directly off `RatePlan`.
- **Date axis** = periods (disjoint per plan). **Party axis** = bands (disjoint
  per period). Orthogonal ⇒ every `(night, party)` resolves to exactly one cell,
  no phantoms, honest grid.
- **Flat pricing** is the degenerate grid: one period, one band (`1..max`).
- **Min-stay**: villa-level `PropertySettings.min_nights_rental` (≈ legacy's
  global default 7); nullable per-period override; multi-period stays take
  `max()` of touched periods (strictest wins).
- **Party-gap coverage**: every period **must** carry a `1..max` base band (no
  silent unpriced guest count); POA is an explicit band. The migration's
  base-weekly fallback (BUG-013) satisfies this by construction.

---

## Blast radius

- **Models / migrations:** delete `RateCard` (+ its EXCLUDE, indexes); reparent
  `RatePeriod` onto `RatePlan`; repoint `RateRule` at `RatePeriod`; move dates +
  `name?`/`min_nights?`/`max_nights?` onto `RatePeriod`; add
  `max_nights_rental?` to `PropertySettings` (reuse the existing
  `min_nights_rental`). `RatePlan` unchanged in shape. Data migration groups flat
  rules into periods (reuse `segmentation.py` + `period_backfill.py`).
- **`Discount.card` FK (nullable) must be repointed** — `Discount` has an
  optional `card` FK + a `discount_card_or_property_required` CHECK
  (`discount.py:14,33`). When `RateCard` dies, either repoint `card → plan`
  (a season-scoped discount) or drop the card scope to property-only and relax
  the constraint. **Decision needed at build; default: property-only** (no prod
  card-scoped discounts exist). `Extra` and inclusions are unaffected — `Extra`
  is property-scoped, and inclusions are already `PropertyService` rows since
  GAP-037 (engine `_derive_inclusions`), *not* a rate field.
- **Engine:** `_load_real_context` no longer keys by card (`rules_by_card` →
  `rules_by_plan`/`by_period`); `pick_rule_for_night` drops the card-precedence
  walk (plan selection by currency stays); `covering_bands` enumerates a period's
  bands. Parity tests must show identical quotes for non-ragged data.
- **Projection / carryover:** unchanged at the plan level (still one plan per
  `(currency, year)`); the year-shift re-expressed against a plan's periods
  instead of its cards.
- **API:** the `/seasons` routes (backed by `RatePlan`) stay but the nested body
  becomes `plan → periods[] → rules[]` (card level removed); add
  `/plans|seasons/{id}/periods`, `/periods/{id}/rules`; resolve the "Season"
  vocabulary (plan-is-Season vs period-is-the-date-window).
- **data_migration loader:** map `VillaSeason(Dates)` + `VillaSeasonRate` +
  `VillaOccupencyPrice` → periods + bands; apply the **checkout-exclusive → inclusive
  trim** before segmentation; recalibrate `reconcile_legacy` expected gaps.
- **Frontend rate-workbench:** matrix rows = periods, cols = bands; per-period
  min/max-night controls; period CRUD; remove card concept from the UI.

## Migration approach

Reuse the BUG-014 machinery: `segment_card_rules` (pure date-axis segmentation)
+ `backfill_card_periods` already group flat rules into disjoint periods and
report ragged cards. Sequence: expand (add period + villa pricing fields,
nullable) → backfill (segment; **trim checkout-exclusive dates first**) →
contract (drop `RateCard`/dates/old EXCLUDEs; add periods-disjoint and
bands-disjoint-party EXCLUDEs; make FKs non-null). Given dev-stage, prioritise
`seed_dev` and the data_migration loader producing the correct shape over
perfect translation of pre-existing dev rows.

## Acceptance

- A villa's rates are `Property → RatePlan → RatePeriod → RateRule`; `RateCard`
  is gone; `RatePlan` keeps currency/basis/validity.
- `RatePeriod` owns dates **and** `min_nights/max_nights`; a villa-level default
  backs unset periods; per-period override works end-to-end (engine honours it).
- Model prevents ragged bands: periods disjoint on date per villa; bands disjoint
  on party per period (EXCLUDE constraints).
- Engine (`quote`, `covering_bands`) produces identical quotes to the pre-change
  model for non-ragged data (parity tests); a ragged fixture proves segmentation
  preserves per-night/per-party prices.
- The rate-workbench matrix relies on a per-period band set (no phantom cells)
  and exposes per-period min/max-night controls.
- The data_migration loader maps legacy → periods+bands with the
  checkout-exclusive date trim; `reconcile_legacy` gaps documented.
- The `/seasons` vocabulary mismatch is resolved (renamed or period-named).

## Dependencies / relations

- **Supersedes [BUG-014](bug-014-raterule-flattened-period-occupancy-hierarchy.md)**
  — its `RatePeriod`, `segmentation.py`, and `period_backfill.py` are the
  foundation here; fold it in rather than shipping it separately against the
  old 4-level tree.
- Pairs with [BUG-013](done/…) — recovered `VillaOccupencyPrice` bands get a
  natural home (period → N band children).
- Coordinate with [BUG-009](../bug-009-price-basis-ignored-by-engine.md) / the
  finance rewrite so the engine contract lands once.
- Related product questions: `q-022-seasons-defined-by-rates.md`,
  `q-023-partial-week-nightly-composition.md`.

## Decided (all open questions resolved 2026-07-01)

- **Model shape** — option **B (thin sheet)**: `Property → RatePlan → RatePeriod
  → RateRule`; drop `RateCard`; keep `RatePlan` as the currency/year sheet
  (confirmed: 23 villas price in ≥2 currencies, engine selects plan by currency).
- **Min/max nights** — nullable override on `RatePeriod`; villa default **reuses
  `PropertySettings.min_nights_rental`** (add `max_nights_rental` if a max default
  is wanted); multi-period stays resolve **strictest-wins** (`min = max()`,
  `max = min()` across touched periods).
- **Named seasons** — **no grouping layer**; add a nullable `name` label on
  `RatePeriod` only.
- **Party-gap policy** — **require a `1..max` base band per period** (editor +
  serializer/DB check); POA only as an explicit band.
- **"Season" vocabulary** — **keep** `/seasons` → `RatePlan`; no rename.

## Adversarial-review corrections folded in (2026-07-01)

Full-dump re-parse + codebase verification against the first draft:

1. Row census corrected: **5,138 raw → 3,668 live true rates** (soft-delete +
   `IsExTra` split); loader must filter both. `TotalNight==span` holds **0/3,668**.
2. **NULL currency on 27% of live rates** (+ ids `0`/`6`) → loader needs an
   explicit NULL→default-currency resolution rule (documented above).
3. **Min/max-nights enforcement is live engine logic** (`RateCard`), not inert
   metadata — dropping the card **relocates** it; parity + new multi-period tests
   required.
4. **Reuse `PropertySettings.min_nights_rental`** for the villa default (exists,
   nullable, currently *unread by the engine*) instead of a new `Property` field.
5. **Universal `−1` date trim** (current loader trims only conditionally on
   adjacency → isolated periods over-count their last night); recalibrate
   `reconcile_legacy`.
6. Migration de-risked: **`QuotationLine` has no `rule` FK** (pure JSON
   `pricing_snapshot`) — RateRule delete+recreate is fully safe.
