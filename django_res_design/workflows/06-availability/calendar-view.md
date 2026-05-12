# Calendar View

Reading the availability calendar.

> ⚠ **Top-of-file warning** — the calendar UI is non-functional in committed legacy code. `<AvailabilityCard />` is `[STUB]`: no CREATE / EDIT / REMOVE handlers, no rendered grid. Treat this entire file as describing *intended* behaviour reconstructed from the dropdown shape and the data calls that *would* feed a working calendar.

## Load availability calendar for a property

**ID:** `AVAILABILITY.CALENDAR.LOAD`
**Trigger:** Navigate to `/Properties/Availability/{PropertyId}` (`Pages/Properties/Availability/Availability.razor`).
**Actor:** Authenticated user.
**Legacy locus:** `Availability.razor:98-124`; `PropertyService2.cs:48` (`LoadAvailabilityStatus`); `ResService.cs:3495` (availability type), `:3523` (`GetLastUpdated`).

### Inputs
- `PropertyId` (route)
- `FromDate`, `ToDate` (UI date pickers — default unclear, likely "next 12 months")
- Implicit: property's `SettingCheckInTime`, `SettingCheckOutTime` (used for half-day rendering)

### Process
1. Load availability type/value: `ResService.ModifyAvailabilityType(type=0, value="", id=PropertyId)` reads `VillaMaster.AvailabilityType` and `VillaMaster.AvailabilityValue` (used only for the URL/Text label).
2. Load status dropdown: `PropertyService2.cs:48` `LoadAvailabilityStatus("5,6,8,9")` runs `SELECT Code as Id, [Name] FROM AvailabilityStatus WHERE Id IN (5,6,8,9)`. The `Code as Id` aliasing is critical: the rows the UI receives carry the **Code** in the `Id` column, so the dropdown's `selectedValue` is the Code (40, 50, 60, 70) — not the `AvailabilityStatus.Id` (5, 6, 8, 9) that was used to filter the SELECT. From `live-db-24-apr.sql:2098-2108`, the filtered rows are:
   - `Id=5 / Code=40 / Name="On Hold"`
   - `Id=6 / Code=50 / Name="Booked"`
   - `Id=8 / Code=60 / Name="Booked VC"`
   - `Id=9 / Code=70 / Name="Available (again)"`
   The Django redesign should refer to these as Codes 40/50/60/70 directly and drop the `AvailabilityStatus.Id` from the wire — it has no meaning to consumers.
3. Last-updated timestamp: `ResService.GetLastUpdated(PropertyId)` → `SELECT TOP 1 format(isnull(UpdatedAt, CreatedAt), 'yyyy-MM-dd HH:mm:ss') FROM VillaAvailability WHERE PropertyId={id} ORDER BY Id DESC`.
4. Render `<AvailabilityCard PropertyId="@PropertyId" />` `[STUB]` — the real calendar is missing from the repo.

### Outputs / side effects
- **No DB writes.**
- UI displays property name, availability-type label, last-updated timestamp, and a placeholder card.

### Failure modes
- Property has no availability rows → last-updated is empty.

### Open questions
- The 4-row status dropdown (40/50/60/70) restricts the staff to those four statuses for manual edits. The redesign should make this list configurable or surface all statuses.
