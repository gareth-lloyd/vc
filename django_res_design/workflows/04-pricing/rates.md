# Rates

A rate is a price applicable to a `(villa, season, date-range, [party size])` tuple, with optional commission / tax / discount / POA / approval flags. Rates can be inside a season or "extra" / "manual" (outside the season's normal date-range pattern).

## Create / update rate

**ID:** `PRICING.RATE.UPSERT`
**Trigger:** Save on `Rates.razor`.
**Actor:** Pricing manager.
**Legacy locus:** `PropertyService.cs:968-1090` (`ModifyRates`); SP `sp_season_rate` (output `@ScopId`).

### Inputs
- `Id` (0 for INSERT), `VillaId`
- `SeasonId` (required unless `IsExtra=true`)
- `IsExtra` (bool — bypass season binding)
- `ArriveDate`, `DepartDate`
- `Name`, `Description`

Pricing:
- `Price`, `PriceType` (nightly / weekly / fixed)
- `WeeklyPrice`, `NightlyPrice`
- `IsPOA` (bool — "Price On Application", suppresses display)

Occupancy:
- `IsOccupationPrice` (bool)
- `PartySize` (int)
- `OccupencyPrice` `[TYPO]`: `List<OccupancyPrice>` for occupancy bands

Commission:
- `CommissionType`, `Commission`, `CommissionNote`

Tax:
- `IsTaxExempt`, `TaxRate`

Discounts (a complex sub-feature):
- `IsDiscount` (bool)
- `DiscountType`, `DiscountRate`, `DiscountNight` (e.g., "stay 7+ nights to qualify"), `DiscountApply`, `DiscountNote`

State:
- `IsApprove` `[TYPO]` — controls visibility in booking engine
- `IsManualUpdate` — prevents bulk-rewrites overriding hand-tuned price
- `CurrencyId`
- `TotalNight` (computed)
- `User`, `Action`

### Process
1. Date validation:
   - `ArriveDate != DepartDate` → "Arrival and departure dates cannot be the same".
   - `DepartDate > ArriveDate` → "Please select a departure date after the arrival date".
   - `(DepartDate - ArriveDate).Days >= 1` → "Please select a arrival and departure date range that results in 1 or more nights".
2. If `!IsExtra`:
   - Find covering season via `GetSeasonValidationParam(..., action=SELECT_WHERE)`.
   - If none → "No rates available at the selected property for the selected arrival date".
   - Pin `SeasonId` from the result.
3. Build 33-param set, execute `sp_season_rate`. Output param `@ScopId` returns the rate id.
4. If `OccupencyPrice` provided: for each band call `ModifyOccupencyPrice` (INSERT or UPDATE).

### Outputs / side effects
- **DB write:** `VillaSeasonRate` row; child `VillaOccupancyPrice` rows.
- **No outbound sync.**

### Failure modes
- Bad date ranges (see validations above).
- No covering season + not `IsExtra` → blocked.
- SP failure → caught, generic error returned.

### Data transformations for storage
- Nights = `(DepartDate - ArriveDate).Days`.
- Commission, tax, discount stored as percentages (decimal) — interpreted at pricing-engine time.

### Open questions
- The 33-parameter SP is a strong signal that the rate concept should be decomposed (price + commission + tax + discount as separate concepts, or at least separate columns wrapped behind a service).
- `IsApprove` typo aside, the approval pathway is sparsely captured. Investigate whether approvals matter operationally or whether they were a planned but unused feature.

---

## Approve rate(s)

**ID:** `PRICING.RATE.APPROVE`, `PRICING.RATE.APPROVE_ALL`
**Trigger:** Approval action(s) on `Rates.razor`.
**Actor:** Pricing manager.
**Legacy locus:** SP `sp_season_rate` with `@Action=APPROVE` or `APPROVE_ALL`.

### Process
1. Execute SP with the approval action; sets `IsApprove=true` on one or all rates.

### Outputs / side effects
- **DB write:** `VillaSeasonRate.IsApprove` flipped.
- Once approved, the pricing engine includes the rate in quotation matching.

### Open questions
- Document whether approval is **required** before a rate can be quoted, or whether `IsApprove=false` rates are still surfaceable.

---

## Delete rate

**ID:** `PRICING.RATE.DELETE`
**Trigger:** Trash on a rate row.
**Actor:** Pricing manager.

### Process
1. `sp_season_rate` with `@Action=DELETE`.
2. Skip date-validation logic on the DELETE path.

### Failure modes
- Rate already attached to a quotation line — unclear, depends on SP cascade behaviour.
