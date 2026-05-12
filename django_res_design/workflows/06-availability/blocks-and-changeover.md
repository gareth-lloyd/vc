# Manual Blocks and Changeover

Both are partially or entirely missing from the committed code; documented here so the Django redesign can fill the gap deliberately.

## Create manual block (owner stay / maintenance)

**ID:** `AVAILABILITY.BLOCK.CREATE` `[STUB]`
**Trigger:** Should be staff drag-select on calendar.
**Actor:** Staff.
**Legacy locus:** **Not implemented** — no UI in `Pages/Properties/Availability/` or `Pages/Availability/`, no service method captured. The `AvailabilityCard` component is a stub.

### Expected inputs (if it existed)
- `PropertyId`, `FromDate`, `ToDate`
- `BlockType` (enum: owner_stay, maintenance, cleaning, etc.)
- `BlockNotes`

### Expected process
- Write `VillaAvailability` rows with status 30 (Unavailable) for the range.
- Use the same `sp_villaAvailability` pattern as holds/bookings.

### Open questions
- The Django redesign needs to add this explicitly — it's a baseline expectation for any vacation rental admin tool.

---

## Edit / remove manual block

**ID:** `AVAILABILITY.BLOCK.EDIT`, `AVAILABILITY.BLOCK.REMOVE` `[STUB]`
**Status:** Not implemented.

### Open questions
- Same as above — design for create/edit/remove + an audit log.

---

## Enforce changeover rules

**ID:** `AVAILABILITY.CHANGEOVER.ENFORCE` `[PARTIAL]`
**Trigger:** Should fire on quotation save and on booking confirmation.
**Actor:** System.
**Legacy locus:** Data exists (`VillaMaster.SettingChangeoverDayId` → `ChangeOverDays` lookup, loaded via `PropertyService2.GetChangeoverDays()`) but the validation step is missing.

### Inputs
- Property's configured changeover day (e.g., Saturday)
- Booking/quote `FromDate.DayOfWeek`

### Expected process
1. On quote/booking save, if `Property.SettingChangeoverDayId` is set:
   - Validate `FromDate.DayOfWeek == changeover_day`.
   - If mismatch → warn and either block or require manager override.

### Outputs / side effects
- Validation rejection.

### Open questions
- Today, the system silently allows arrival on any day. Decide whether enforcement is a hard rule, a soft warning, or a per-property toggle.
- Changeover behaviour interacts with same-day handover (one party departs morning, another arrives afternoon) — the half-day boundary in `sp_getAvailability` already handles the *display* of this; enforcement should be coherent with it.
