# Property Master

The overview and operational-settings workflows on a property. Each operates on a slice of the legacy `VillaMaster` / `VillaSettings` god-objects.

## Save property overview details

**ID:** `CATALOG.PROPERTY.UPDATE_OVERVIEW`
**Trigger:** Save button on the Overview tab of `/property-detail/{PropertyId}` (`PropertyOverviewGeneral.razor`).
**Actor:** Property manager.
**Legacy locus:** `PropertyOverviewGeneral.razor:186, 421-440`; `PropertyService.GetUpdatePropertyById` (`PropertyService.cs:283-332`); SP `sp_save_property`.

### Inputs
- Identity: `Id` (property id), `Action`, `User`
- Naming: `Name`, `DisplayName`
- Classification: `Category` (FK `VillaPropertyCategory`), `GroupId` (FK `VillaGroup`)
- Geo: `Latitude`, `Longitude` (strings), `AddressLine1/2/3`, `LocalityRegion`, `LocalityTown`, `PostCode`, `CountryId`, `RegionId`
- Capacity: `Guests`, `AdditionalGuests`, `Bedrooms`, `Ensuites`, `Bathrooms`, `Size`
- Regulatory: `LicenceNumber`
- Content: `HouseRules`
- External link: `ZohoId`
- Source: `Channel` (`EChannel` enum)

### Process
1. `PropertyService.GetUpdatePropertyById(...DbAction.UPDATE)` builds a 22-parameter set.
2. Execute SP `sp_save_property` (`@Action`, `@Id`, `@Name`, `@DisplayName`, ...).
3. If `IsApiExecute(action) && AllowSyncOnUpdate() > 0`:
   - `UpdateSyncId(ResModule.VILLA, propertyId, 0, userId, UPDATE)`
   - `_apiService.VillaSync(SyncPostData<string>{ ApiAction, Id, LoggedUser, Data="VILLA_DETAILS" })` — fire-and-forget.

### Outputs / side effects
- **DB write:** `VillaMaster` (UPDATE; the form path covers UPDATE, not INSERT — creation is via a different code path not captured).
- **Sync queue:** module `VILLA`, data variant `VILLA_DETAILS`.
- **Outbound push:** see `INTEGRATIONS.PUBLIC_API.VILLA_SYNC`.
- **Zoho push:** referenced as `VillaSync` but the actual Zoho call is `PushZohoVilla` to module `VILLLA_MASTER` `[TYPO]` (see `11-integrations/zoho-crm.md`).
- **In-memory cache:** `SharedService.SetProperty()` updates the open page's cached property reference.

### Data transformations for storage
- Numeric fields coerced via `Utilities.ChangeType<int>()` — quiet failures yield `0`.
- Latitude/Longitude stored as strings (no spatial type), concatenated to `"{lat},{lon}"` for Zoho's `Co_ordinates` field downstream.

### Failure modes
- `propertyId <= 0` → silent return (`PropertyOverviewGeneral.razor:425`).
- SP failure → `Response.Status = false`, generic "Fail to load property" message.
- Sync failure → logged silently after DB commit.

### Open questions
- Latitude/Longitude as strings → use Django's `geography` (PostGIS Point) in the redesign; round-trip safely to Zoho's string format at the integration layer.

---

## Set property website status

**ID:** `CATALOG.PROPERTY.SET_WEBSITE_STATUS`
**Trigger:** Status dropdown change on `PropertyOverviewWebisteStatus.razor` `[TYPO]` save.
**Actor:** Property manager.
**Legacy locus:** `PropertyService.UpdateWebsiteStatus` (`PropertyService.cs:555-570`).

### Inputs
- `PropertyId`
- `StatusId` (FK `vw_VillaStatus` — view, not table)
- `userId`

### Process
1. Validate both `> 0`; else return.
2. **Raw SQL** (`PropertyService.cs:564`):
   ```sql
   UPDATE VillaMaster SET ViilaStatus = {StatusId}, SyncId = 0 WHERE Id = {PropertyId}
   ```
   `[TYPO]` column name `ViilaStatus` (double-i).
3. If sync allowed: `UpdateSyncId(ResModule.VILLA, ..., UPDATE)` and `VillaSync` with `Data="STATUS_DETAILS"`.

### Outputs / side effects
- **DB write:** `VillaMaster.ViilaStatus`, `VillaMaster.SyncId=0`.
- **Outbound push:** villa sync, status variant.

### Failure modes
- **SQL injection risk** `[SECURITY]` — raw SQL with string concatenation. `PropertyId` and `StatusId` are parsed `int`s before the call so the risk is mitigated in practice, but the pattern is unsafe.

### Open questions
- Column `ViilaStatus` is a typo — fix during migration.
- Status is set without writing an audit row of the transition. Add a `PropertyStatusEvent` to the redesign.

---

## Configure operational settings (check-in/out, min nights, currency, etc.)

**ID:** `CATALOG.PROPERTY.UPDATE_SETTINGS`
**Trigger:** Save on the Settings tab.
**Actor:** Property manager.
**Legacy locus:** `PropertyService2.cs:559-657` (`SaveVillaPropertySettingsDetails`); SP `sp_crud_villasettings`.

### Inputs
Each "real" value is paired with an `IsDefaultSetting*` boolean — when `true`, the value is read from `VillaConfigPropertyDefault` instead of the property's own column.

Pairs:
- Availability: `IsDefaultSettingAvailability` / `SettingAvailabilityStatusId`
- Booking approval: `IsDefaultBookingPreApprove` / `SettingIsBookingsRequirePreApproval`
- Prices-entered mode: `IsDefaultSettingPricesEnteredTypeId` / `SettingPricesEnteredTypeId`
- Currency: `IsDefaultSettingCurrencyId` / `SettingCurrencyId`
- Check-in time: `IsDefaultSettingCheckInTime` / `SettingCheckInTime` (TimeSpan parsed from `strSettingCheckInTime`)
- Check-out time: `IsDefaultSettingCheckOutTime` / `SettingCheckOutTime`
- Changeover day: `IsDefaultSettingChangeoverDayId` / `SettingChangeoverDayId` (FK `ChangeOverDays`)
- Min nights: `IsDefaultSettingMinNightsRental` / `SettingMinNightsRental` + `SettingMinNightsRentalNote`
- Nightly price: `SettingNightlyPrice` (no default-flag pair)
- Manual-update marker: `IsManualUpdate`

### Process
1. Parse time strings: `TimeSpan.TryParse(strSettingCheckInTime, ...)` (returns `00:00:00` silently on parse failure).
2. Build 23 parameters, execute `sp_crud_villasettings`.
3. **Post-load defaulting**: on the read response, if `IsDefault*` is true, replace the returned value with the corresponding `_defaultProperty` field (`PropertyService2.cs:639-657`).

### Outputs / side effects
- **DB write:** `VillaSettings` row.
- Response carries values with defaults already applied.
- **No outbound sync** of settings — they're consumed locally by quotation/booking flows.

### Failure modes
- Bad time string → silent `00:00:00`.
- `VillaId <= 0` → SP fails.

### Open questions
- Replace the `IsDefault*` + value pattern with **nullable column + `effective_*()` resolver** — the redesign plan in `../03-finance-config.md` does this for finance; do the same for these settings.
- Changeover day is *read* but never enforced (see `06-availability/changeover-rules.md`).
