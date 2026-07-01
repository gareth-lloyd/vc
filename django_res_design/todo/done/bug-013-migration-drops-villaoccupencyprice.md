> **✅ RESOLVED (2026-07-01)** — `RateRuleLoader` now recovers occupancy bands.
> The `legacy_query` LEFT JOINs `VillaOccupencyPrice`, and `_prepare_occupancy_rows`
> expands each `IsOccupationPrice` parent into one RateRule per valid band
> (`legacy_id="occ-{OccId}"`, `OccupencyPrice` as weekly) plus base-weekly gap
> fallback rules (`occ-fb-{parent}-{k}`) over the party ranges the bands leave
> uncovered — so a guest count matching no band still gets the legacy base-weekly
> quote (full parity). Invalid bands (null/≤0 bound, `From>To`, null/0 price) are
> dropped; the fallback covers their range. `reconcile_legacy` counts both legacy
> sources; `expected_gap` stays a placeholder to recalibrate at the first cutover
> dry-run. Shipped to local `main` in `e7cbcc8` / `276a1d9` / `2b5a5a1`; see
> `data_migration/CUTOVER.md` § "Occupancy-band pricing (BUG-013)" for the
> band-vs-simple precedence cutover-verification note.

# BUG-013 — Migration silently drops `VillaOccupencyPrice` (range-based occupancy rates lost)

- **Severity:** 🔴 Bug (data + behaviour loss on cutover) — villas that priced by
  occupancy band in legacy come across with **no** banded pricing.
- **Source:** 2026-07-01 rate-workbench UX investigation (adversarial review of the
  ragged-rule question). Surfaced while confirming what shape migrated rate data
  actually takes.
- **Files:**
  - legacy entity: `ResSystem/Database/Data/VillaOccupencyPrice.cs`
    (`VillaSeasonRateId`, `OccupencyPrice`, `OccupencyFrom`, `OccupencyTo`)
  - legacy quote-time use: `ResSystem/NewResSystem.Core/Services/ResService/ResService.cs:1211-1217`
  - migration: `django_res/data_migration/loaders/pricing.py` (`RateRuleLoader`
    ~374-481; SQL ~388-392 selects `PartySize` only; party mapping 439-445)
  - migration registry: `django_res/data_migration/registry.py` (no occupancy loader)
  - target: `django_res/pricing/models/rate.py` (`RateRule.min_party`/`max_party` 84-102)

## Problem

Legacy has **two** ways to price a period (`VillaSeasonRate`):

1. **Simple** — the rate row carries a single `PartySize` + price.
2. **Occupancy pricing** (`IsOccupationPrice = TRUE`) — the rate row is a parent
   and **child `VillaOccupencyPrice` rows** carry `(OccupencyFrom, OccupencyTo,
   OccupencyPrice)` bands (e.g. 2–4 → €500, 5–6 → €700). Legacy quotes off these
   at request time: `ResService.cs:1211-1217` selects the children for the rate and
   picks the band where `args.Guests` is between `OccupencyFrom` and `OccupencyTo`.

The migration only ports **path 1**. `RateRuleLoader` reads `VillaSeasonRate`
alone (`pricing.py` SQL ~388-392) and derives occupancy purely from the parent's
`PartySize` (`pricing.py:439-445`):

- `PartySize` set → `min_party = max_party = PartySize` (a **single-point** band)
- `PartySize` null → `min_party = 1, max_party = capacity` (**unbounded**)

`VillaOccupencyPrice` is **never queried** — there is no occupancy loader in
`registry.py`, and `grep -i occupenc django_res/data_migration/` returns nothing.
The loader docstring even states the contract as bare `VillaSeasonRate → RateRule`
with no mention of the children.

**Consequences:**

- Villas that used occupancy pricing lose all their banded rates on cutover;
  they come across with only the parent's `PartySize` band (often a single point
  or unbounded), so the engine will mis-price or fail to cover real party sizes.
- The migrated dataset has almost **no genuine range-based occupancy bands**,
  which undercuts features built to consume them — notably GAP-044's occupancy
  fan-out (`covering_bands`), which is enumerating banding that mostly isn't there.
- New-vs-legacy quote parity is broken for these villas (violates the
  "follow legacy for customer-facing" principle).

## Proposed fix

1. Add an **occupancy-price loader** (or fold into `RateRuleLoader`) that, when a
   `VillaSeasonRate` has `IsOccupationPrice = TRUE`, emits **one `RateRule` per
   child `VillaOccupencyPrice`** over the parent's date range:
   `date_from/date_to` = parent period; `min_party/max_party` = `OccupencyFrom/To`;
   `nightly`/`weekly` derived from `OccupencyPrice` (legacy stores weekly and a
   computed `NightlyPrice = OccupencyPrice / 7`).
2. Feed those rules through the existing `resolve_rate_rule_overlaps`
   (`pricing.py:167-276`) so the EXCLUDE constraint (card × daterange × party) is
   respected — occupancy bands within one legacy period are disjoint by
   construction, so they should slot in cleanly.
3. Keep it **idempotent** (re-loadable) per `CUTOVER.md`, and update the loader
   docstring + `registry.py` to reflect the child loader.
4. Update the CUTOVER gap accounting for the newly-recovered rows.

## Acceptance

- A legacy villa with `IsOccupationPrice` rates comes across with one `RateRule`
  per occupancy band (verified against a known villa's legacy `VillaOccupencyPrice`
  rows).
- The engine quotes the same band the legacy `ResService` would for a given guest
  count (parity spot-check).
- Loader is idempotent; a second run is a no-op.
- `grep -i occupenc django_res/data_migration/` is no longer empty.

## Dependencies / relations

- Prerequisite reality behind [BUG-014](bug-014-raterule-flattened-period-occupancy-hierarchy.md)
  (the flattened `RateRule` shape that made this easy to drop) — fixing BUG-014's
  hierarchy would give these bands a natural home.
- Feeds GAP-044 (occupancy fan-out) — that feature needs real banded data to be
  meaningful.
- Sibling RateRule integrity tickets: BUG-002 (zero-length range),
  BUG-003 (POA vs price).
- See `q-022-seasons-defined-by-rates.md` for the season/rate modelling context.
