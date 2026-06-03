# Seasons

A season groups one or more (possibly non-contiguous) date ranges for a single villa, with shared notes, inclusions, and commission settings. Rates are attached **to** a season.

## Create / update season (with date ranges and optional bulk rates)

**ID:** `PRICING.SEASON.UPSERT`
**Trigger:** Save on `Season.razor`.
**Actor:** Pricing manager.
**Legacy locus:** `PropertyService.cs:708-870` (`ModifySeason`); SPs `sp_seasons`, `sp_seasonDates`, `sp_validateSeason`.

### Inputs
Season header:
- `Id` (0 for INSERT)
- `VillaId`
- `Name` (required, except for `COPY` action)
- `Notes`
- `Inclusion` (what the rate includes — e.g., "Daily housekeeping, welcome basket")
- `CarriedRates` (bool — copy rates from another season; the COPY action uses this)
- `PriceType` (int — nightly / weekly / fixed)
- `CommissionType`, `Commission` (decimal)
- `IsOccupationPrice` (bool — pricing varies by guest count)
- `Action` (`INSERT` | `UPDATE` | `DELETE` | `COPY` | `SELECT`)

Date ranges (a season can hold many):
- `Dates`: `List<SeasonsDates>` with `FromDate`, `ToDate`

Optional bulk-rates payload (creates rates immediately along with the season):
- `Rates`: `List<RatesModel>` — see `rates.md`

### Process
1. Validate `Name` non-empty.
2. Validate `Dates` non-empty.
3. For each date: assert `FromDate < ToDate`.
4. Cross-check the supplied `Dates` list against itself: no duplicates, no overlaps (`PropertyService.cs:732-754`).
5. For each date, run `sp_validateSeason` with `(VillaId, FromDate, ToDate)` to check against existing seasons. Any returned row means overlap → return `"Selected dates overlap with another season"`.
6. Execute `sp_seasons` with the supplied `@Action` to upsert the season header. Output param holds the season `Id`.
7. **Date rows are rewritten** on UPDATE: delete-and-re-insert pattern. For each `SeasonsDates`: run `sp_seasonDates` with the appropriate action.
8. If `Rates` provided:
   - Project to `VillaSeasonRate` POCOs (`PropertyService.cs:808-833`), marking each `IsManualUpdate=true`.
   - `BulkInsertAsync(rates.ToDataTable(), "VillaSeasonRate", _columnMap_)`.

### Outputs / side effects
- **DB write:** `VillaSeasons` (1 row), `VillaSeasonDates` (N rows), `VillaSeasonRate` (M rows if bulk rates included).
- **No outbound sync.**

### Failure modes
- Empty `Name` → `"Please enter season name"`.
- Empty `Dates` → validation error.
- Duplicates within `Dates` → `"Please enter none duplicate date ranges"`.
- Internal overlaps → `"Entered date ranges overlap"`.
- External overlap → `"Selected dates overlap with another season"` (from `sp_validateSeason`).

### Data transformations for storage
- Dates parsed to `DateTime` from UI pickers.
- Bulk-insert rates flag `IsManualUpdate=true` so subsequent automated bulk recalculations leave them alone.

### Open questions
- Delete-and-re-insert of dates is concurrency-unsafe and breaks the FKs in `VillaSeasonRate` if rates were already pinned to those date ranges. Django redesign should diff and patch.
- Overlap enforcement should move to a Postgres `EXCLUDE` constraint instead of an SP-based pre-check.

---

## Delete season

**ID:** `PRICING.SEASON.DELETE`
**Trigger:** Trash icon on a season.
**Actor:** Pricing manager.
**Legacy locus:** Same `ModifySeason` path with `Action=DELETE`.

### Process
1. `sp_seasons` with `@Action=DELETE`.
2. Cascading delete (or soft-delete) of `VillaSeasonDates` and `VillaSeasonRate` rows is handled inside the SP.

### Failure modes
- Season referenced by an existing booking line — unclear; likely soft-deletes leaving FKs intact.

---

## Copy season (from another)

**ID:** `PRICING.SEASON.COPY`
**Trigger:** "Copy" action on a season — typically used to clone last year's pricing to the new year.
**Actor:** Pricing manager.
**Legacy locus:** `ModifySeason` with `Action=COPY` and `CarriedRates=true`.

### Inputs
- Source season `Id`, target `Dates` (the new dates), `CarriedRates=true`.

### Process
1. `sp_seasons` with `Action=COPY` carries the season header.
2. New `VillaSeasonDates` rows written for the target dates.
3. Rates from the source are duplicated (handled inside SP; not visible in committed code).

### Redesign — next-year quoting via lazy projection (no default clone)

The legacy manual "Copy" is no longer the default next-year path. Instead, a quote that lands
on a year with no `RatePlan` is priced by **lazy projection**: `PricingEngine.quote()` derives a
guide rate at quote time from the most recent year that has rates
(`RateProjectionService.project`), flags `Quote.is_projected`, and writes nothing (see
`04-pricing.md` "Projected pricing for future years"). The redesign resolves the legacy open
questions as follows:

- **No default clone, no `is_provisional`.** Because the guide is derived at quote time and not
  stored, there is no per-rule "provisional" flag and no `carry_over_rates` beat task rolling
  the whole portfolio forward. The synthesized in-memory rows carry the source rows' pks, so the
  quote breakdown still traces back to the real anchor rules. A projected quote renders an
  "inquire for accurate rate" marker via `Quote.is_projected`.
- **Date mapping is an injected, swappable function** (`date_map`), defaulting to
  changeover-weekday alignment, and shared by projection and the on-demand carry-forward.
  Whether the business wants weekday-alignment or same-calendar-date is an **open follow-up**
  pending Bryony's listing Loom — see `10-decisions.md` "Carryover date-mapping rule". It now
  gates the default quoting path, so the default matters more than under the old design.
- **Promoting a year to editable rows is on-demand**, not automatic:
  `RateCarryoverService.materialise(property, *, target_year, currency, date_map, uplift)` clones
  the anchor year into real `RatePlan`/`RateCard`/`RateRule` rows (idempotent per
  `(property, currency, target_year)`, provenance in `RatePlan.notes`), exposed as a `RatePlan`
  admin action and `POST /properties/{id}/seasons:carry-forward`. Materialised rows are ordinary
  editable rules with no provisional flag. Manual ad-hoc copy of one season to arbitrary dates
  remains available in the admin for cloning that isn't a straight year roll-forward.
