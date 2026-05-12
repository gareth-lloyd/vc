# Pricing Engine

How the legacy system priced a quotation request. This is the synthesis workflow that feeds `GetQuotationData` and powers the quotation builder UI.

## Compute prices for a quotation request

**ID:** `PRICING.ENGINE.COMPUTE_QUOTATION`
**Trigger:** Called by the quotation construction flow (`QUOTATION.BUILD.SEARCH_OPTIONS`) every time the user changes dates, property selection, or guest count.
**Actor:** System (synchronous, in the foreground).
**Legacy locus:** `ResService.cs:1881-2300+` (`GetQuotationData` and `ProcessQuotationItemAsync`); SPs `sp_getQuotationData`, `sp_getQuotationPrices`, `sp_getAvailability`.

### Inputs
- `QuotationArgs`: `FromDate`, `ToDate`, `VillaId` (or property filters: `Minbed`, `Maxbed`, `CountryId`, `RegionIds`, `FeatureIds`), `Adults`, `Children`, `Guests`, `IsSpecificDate`, `IsUnbrandedVilla`, `PreferenceId`.

### Process
1. **Property candidate list**:
   - Execute `sp_getQuotationData` with filters → returns candidate villas with base info (currency, commission, tax, etc.).
2. **For each candidate villa**:
   a. **Availability** — `sp_getAvailability(villaId, fromDate, toDate)` → list of blocked nights (statuses 30/40/50/60). The engine considers everything else available.
   b. **Changeover-day shift** (`ResService.cs:2028-2041`) — if `item.SettingChangeoverDayId != -1` (i.e. the property has a fixed weekly changeover), the engine advances `startDate` forward day-by-day until `startDate.DayOfWeek == SettingChangeoverDayId`, then uses the shifted date for the pricing window. Sentinel `-1` means "open / flexible" and is exposed to the caller as `item.ChangeOverDay = "open/flexible"`. The shift is silent — the caller does not see how many nights were dropped.
   c. **Rates** — `sp_getQuotationPrices(villaId, fromDate, toDate)` → applicable `VillaSeasonRate` rows.
   d. **Rate selection per night** (the inner loop):
      - For each night between `FromDate` and `ToDate`, find the rate whose `[FromDate, ToDate]` covers the night.
      - If `rate.IsOccupationPrice == true`: load `VillaOccupancyPrice` bands for the rate. Match by `OccupencyFrom <= Guests <= OccupencyTo`. Use the matching band's `OccupencyPrice` as the nightly price. (First-match-by-row when bands overlap.)
      - Else: use `rate.WeeklyPrice / 7` as nightly.
   e. **Accumulate `weeklyPrice`** = sum of all nightly prices in the period.
   f. **Apply commission**: per `RatesModel.Calculate()`:
      - If `CommissionType == 10` (percentage): `commission = weeklyPrice × Commission / 100`.
      - Else (fixed): `commission = Commission`.
   g. **Apply tax**: if `!IsTaxExempt`: `tax = net × TaxPercentage / 100`.
   h. **Apply discount**: if `IsDiscount` and `nights >= DiscountNight`: subtract `DiscountRate × applicable basis`.
   i. **POA flag**: if `rate.IsPOA == true`, suppress the price in the result (set marker for "Price On Application").
   j. **Availability flags**: set `IsBook=true` if any covered night has booking-status; `IsHold=true` if any has hold-status; result still returned (allows quoting on partially-blocked dates with a warning).
3. **Filter** results by guest count (must fit `Guests`), min/max price band, feature presence.
4. **Return** `List<QuotationPageModel>` — each villa with its computed `QuotationPriceModel` (Gross, Currency, Inclusion, IsBook, IsHold).

### Outputs / side effects
- **No DB writes** — the engine is pure compute on read.
- UI binds the list to the quotation builder.

### Data transformations for storage
- Inputs are dates/integers; outputs include `GrossPrice` (decimal), `Currency`, `CurrencySymbol` for display.
- Rates' currency may differ across villas in the same result set — the UI presents each villa's price in its own currency.

### Failure modes
- No rates cover the requested date → engine returns the villa with `GrossPrice=0` or with `IsPOA=true` marker, depending on what the rate selection produces.
- Multiple covering rates → first-match-by-row.
- Occupancy band mismatch (guest count outside all bands) → rate falls back to `WeeklyPrice / 7` for that night.

### Open questions
- The Django redesign plans a stateless `pricing.services.PricingEngine` (see `../04-pricing.md`). It should:
  - Make rate selection deterministic (priority + explicit tiebreak).
  - Make occupancy-band selection explicit (closed intervals, no overlaps via DB constraint).
  - Centralise commission / tax / discount math in a `Quote` value object rather than the rate row.
  - Surface POA and partial-block clearly in the API response.
- FX rate is **never applied** in the legacy engine — each villa quotes in its own currency. If the redesign needs cross-currency totals, an FxRate table and conversion service are needed.
- The legacy engine **does** apply changeover-day adjustment (`ResService.cs:2028-2041`), but only by silently advancing the `startDate` — it does not reject the request, surface the dropped nights, or attempt the symmetric trailing trim. The Django port should reject (or explicitly snap-and-warn) requests whose `from_date` does not fall on the property's changeover day, rather than mutating the inputs invisibly.
