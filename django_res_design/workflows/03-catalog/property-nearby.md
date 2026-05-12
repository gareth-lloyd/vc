# Property Nearby

Points of interest (restaurants, beaches, attractions) attached to a property, with a distance and access-method flags.

## Manage nearby place

**ID:** `CATALOG.PROPERTY_NEARBY.UPSERT`, `CATALOG.PROPERTY_NEARBY.DELETE`
**Trigger:** Save / delete on `PropertyNearBy.razor`.
**Actor:** Property manager.
**Legacy locus:** `PropertyService.cs:1196-1245` (`GetAllPropertyNearby`); SP `SP_CRUD_PropertyNearByLocationType`.

### Inputs
- `Id` (0 for INSERT)
- `PropertyId`
- `PropertyNearByLocationTypeId` (FK `VillaNearByLocationType` — e.g., restaurant, beach, airport)
- `Name` (place name)
- `Description`
- `Distance` (decimal; unit not modelled — implicit km or miles depending on locale)
- Access methods (booleans): `ByBoat`, `ByDrive`, `ByWalk`
- `UserId`
- `Action`

### Process
1. Build parameters via `GetAllPropertyNearbyParam`.
2. Execute SP.
3. On success and `IsApiExecute(action)`:
   - `UpdateSyncId(ResModule.VILLA_LOCATION, PropertyId, 0, UserId, UPDATE)`
   - `_apiService.VillaNearByAsync(SyncPostData<int>)`.

### Outputs / side effects
- **DB write:** `VillaPropertyNearBy` (or similarly named) row.
- **Outbound push:** `INTEGRATIONS.PUBLIC_API.VILLA_NEARBY_SYNC` (`/WP_Sync_Villa` with nearby variant).

### Data transformations for storage
- `Distance` stored as decimal; the unit is implicit.

### Failure modes
- `PropertyId <= 0` → SP silently no-ops.
- `LocationTypeId <= 0` → FK violation.

### Open questions
- Model distance as `(value, unit)` so the displayed unit is unambiguous.
- The Django redesign (`../02-properties.md`) plans for `Property.nearby` as a JSONB-or-related model — these workflows map there.
