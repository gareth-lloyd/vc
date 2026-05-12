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

### Open questions
- Behaviour of `IsManualUpdate` flag on copied rates is unclear — should the copy inherit it or reset to `false`?
