# Occupancy Pricing

When a rate has `IsOccupationPrice=true`, the price varies by guest count. Each occupancy band specifies `OccupencyPriceFrom..OccupencyPriceTo` and a `OccupencyPrice` `[TYPO]` (all "Occupancy"). Bands can be non-contiguous and overlap — the engine picks the first match.

## Manage occupancy band

**ID:** `PRICING.OCCUPANCY.UPSERT`, `PRICING.OCCUPANCY.DELETE`, `PRICING.OCCUPANCY.LIST`
**Trigger:** Save / delete on an occupancy-band sub-form inside `Rates.razor`. Triggered recursively from the rate-upsert workflow.
**Actor:** Pricing manager.
**Legacy locus:** `PropertyService.cs:1101-1130` (`ModifyOccupencyPrice`); SP `sp_occupency_price`.

### Inputs
- `Id` (0 for INSERT)
- `RateId` → SP param `@VillaSeasonRateId`
- `OccupencyPriceFrom`, `OccupencyPriceTo` (ints — guest-count range, inclusive)
- `OccupencyPrice` (decimal)
- `Action` (`INSERT` | `UPDATE` | `DELETE` | `SELECT_ALL`)

### Process
1. Build 5 parameters: `@Id`, `@VillaSeasonRateId`, `@OccupencyPrice`, `@OccupencyPriceFrom`, `@OccupencyPriceTo`, `@Action`.
2. Execute `sp_occupency_price`.
3. For `SELECT_ALL`: returns `List<OccupancyPrice>` for the rate.

### Outputs / side effects
- **DB write:** `VillaOccupancyPrice` row(s).
- **No outbound sync.**

### Data transformations for storage
- `From`/`To` are stored verbatim. No constraint that `From <= To`. No constraint against overlap between bands.

### Failure modes
- `From > To` → SP may silently skip or store inverted values.
- Overlapping bands → both stored; engine picks the first matching by row order.

### Open questions
- Add range-overlap constraints in the Django redesign (`EXCLUDE USING gist (rate_id WITH =, int4range(from_, to_, '[]') WITH &&)`).
- Decide explicitly what "guest count = 5 falls in bands [4..6] and [5..8]" means — first-match-by-row is opaque.
