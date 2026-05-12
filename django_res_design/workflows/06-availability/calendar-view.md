# Calendar View

Reading the availability calendar.

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
2. Load status dropdown: `PropertyService.LoadAvailabilityStatus("5,6,8,9")` runs the SQL `SELECT Code as Id, [Name] FROM AvailabilityStatus WHERE Id IN (5,6,8,9)` → returns On Hold (40), Booked (50), Booked VC (60), Available Again (70).
3. Last-updated timestamp: `ResService.GetLastUpdated(PropertyId)` → `SELECT TOP 1 format(isnull(UpdatedAt, CreatedAt), 'yyyy-MM-dd HH:mm:ss') FROM VillaAvailability WHERE PropertyId={id} ORDER BY Id DESC`.
4. Render `<AvailabilityCard PropertyId="@PropertyId" />` `[STUB]` — the real calendar is missing from the repo.

### Outputs / side effects
- **No DB writes.**
- UI displays property name, availability-type label, last-updated timestamp, and a placeholder card.

### Failure modes
- Property has no availability rows → last-updated is empty.

### Open questions
- The 4-row status dropdown (40/50/60/70) restricts the staff to those four statuses for manual edits. The redesign should make this list configurable or surface all statuses.
