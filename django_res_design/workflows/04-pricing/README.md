# 04 · Pricing

Seasons, rates within seasons, occupancy-based per-night pricing, and the pricing engine that powers quotation generation. The engine is the heart of the system — `GetQuotationData` is several hundred lines and dictates the shape of `QuotationPriceModel` returned to the UI.

## Files

| File | Workflows |
|---|---|
| [`seasons.md`](./seasons.md) | Create season (single or multi-range), update season, delete season, copy season |
| [`rates.md`](./rates.md) | Create rate (within a season, or as extra/manual rate), update rate, delete rate, approve rate(s) |
| [`occupancy-pricing.md`](./occupancy-pricing.md) | Set / update / delete occupancy-band prices for a rate |
| [`pricing-engine.md`](./pricing-engine.md) | How `GetQuotationData` computes prices for a quotation request |

## Entities touched

- `VillaSeasons` — `Id`, `VillaId`, `Name`, `Notes`, `Inclusion`, `PriceType`, `CommissionType`, `Commission`, `IsOccupationPrice`
- `VillaSeasonDates` — multiple per season (non-contiguous date ranges): `SeasonId`, `FromDate`, `ToDate`
- `VillaSeasonRate` — `SeasonId`, `VillaId`, `FromDate`, `ToDate`, `PartySize`, `Price`, `PriceType`, `WeeklyPrice`, `NightlyPrice`, `Commission`, `CommissionType`, `CommissionNote`, `TaxRate`, `IsTaxExempt`, `IsDiscount`, `DiscountType`, `DiscountRate`, `DiscountApply`, `DiscountNote`, `DiscountNight`, `IsOccupationPrice`, `IsApprove` `[TYPO]`, `IsPOA`, `CurrencyId`, `IsManualUpdate`, `IsExtra`
- `VillaOccupancyPrice` — `VillaSeasonRateId`, `OccupencyPriceFrom`, `OccupencyPriceTo`, `OccupencyPrice` (all `[TYPO]` of "Occupancy")

## Stored procedures

- `sp_seasons` — season CRUD
- `sp_seasonDates` — season-date-range rows (multiple per season)
- `sp_validateSeason` — overlap check (returns rows when overlap detected)
- `sp_season_rate` — rate CRUD; output `@ScopId`
- `sp_occupency_price` `[TYPO]` — occupancy band CRUD
- `sp_getQuotationData`, `sp_getQuotationPrices`, `sp_getAvailability` — used by the pricing engine

## Cross-cutting concerns

- **No outbound sync** for pricing — all rates are computed server-side during quotation, never pushed to WordPress.
- **Currency is per-rate** (`VillaSeasonRate.CurrencyId`); the system supports mixed currencies on one quote.
- **Approval workflow** is implicit: rates have `IsApprove` `[TYPO]` and an `APPROVE` / `APPROVE_ALL` SP action exists but is not strongly visible in committed pages.
- **Manual override marker**: `IsManualUpdate` on both rate and finance rows prevents bulk-rewrites from clobbering hand-tuned values.

## Open design questions for the Django redesign

- The data model (`../04-pricing.md`) plans `RatePlan`, `RateRule`, `Surcharge`, `Discount`, `ChangeOverRule`, `Currency`, `FxRate`, and a `PricingEngine` service. The legacy shape (seasons + rates + occupancy-bands all in flat tables) is the **as-is**; the redesign is more normalised.
- Multi-range seasons (one season → many `VillaSeasonDates` rows) is a useful feature to preserve.
- The legacy overlap detection (`sp_validateSeason`) is server-enforced — Django redesign should use `EXCLUDE USING gist (villa_id WITH =, daterange(from_date, to_date) WITH &&)`.
- The "occupancy band" idea (price varies by `OccupencyFrom..OccupencyTo` guest count) is worth preserving but the typo and the band-gap allowance (no contiguity enforcement) should be fixed.
