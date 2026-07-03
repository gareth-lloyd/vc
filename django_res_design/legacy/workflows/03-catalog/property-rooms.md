# Property Rooms

Rooms are owned by a property and tagged with a "placement" (Ground Floor, First Floor, etc.). Bed counts are denormalised onto the room row (one column per bed type) rather than modelled as a child table.

## Save (create / update / delete) room

**ID:** `CATALOG.ROOM.UPSERT`, `CATALOG.ROOM.DELETE`
**Trigger:** Save / delete on `PropertyRooms.razor`.
**Actor:** Property manager.
**Legacy locus:** `PropertyService2.cs:241-310`; SP `sp_crud_VillaRooms` (alias `SP_CRUD_VILLAROOMS`).

### Inputs
- `Id` (0 for INSERT)
- `VillaId` (required, > 0)
- `Name` (required)
- `PlacementId` (FK `VillaRoomsPlacement`, required > 0)
- Bed counts (int each): `BedDouble`, `BedTwinDouble`, `BedTwin`, `BedSingle`, `BedBunk`, `BedSofa`, `BedChildrens` `[TYPO]` (intended `Childrens`/`Children's`)
- `IsEnsuit` `[TYPO]` (intended `IsEnsuite`)
- `WebsiteDescription` (marketing text)
- `VCNotes` (internal notes)
- `UserId` (audit)
- `Action`

### Process
1. Validation: `VillaId > 0`, `Name` non-empty, `PlacementId > 0` (`PropertyService2.cs:251-264`).
2. Build 12+ parameters, execute SP.
3. On success, if `IsApiExecute(action)`: `UpdateSyncId(ResModule.VILLA_ROOMS, VillaId, 0, UserId, UPDATE)` and `_apiService.VillaRoomsSync(SyncPostData)`.

### Outputs / side effects
- **DB write:** `VillaRooms`.
- **Outbound push:** `INTEGRATIONS.PUBLIC_API.VILLA_ROOMS_SYNC` (`/WP_Sync_Villa` with rooms-variant payload).

### Failure modes
- Validation failures return distinct messages: "Invalid property details", "Please input valid name", "Please select placement".

### Open questions
- Fix typos (`IsEnsuit`, `BedChildrens`) in the redesign.
- Bed counts as 7 nullable ints is OK but a child `Bed` model with `type` + `count` would be more flexible.

---

## Manage room placement

**ID:** `CATALOG.ROOM_PLACEMENT.UPSERT`, `CATALOG.ROOM_PLACEMENT.DELETE`
**Trigger:** Admin modal under the rooms page.
**Actor:** Administrator.
**Legacy locus:** `PropertyService2.cs:355-385`; SP `sp_crud_VillaRoomsPlacement`.

### Inputs
- `Id`, `Name` (required), `UserId`, `Action`

### Process
1. Validate `Name` non-empty.
2. Execute SP.

### Outputs / side effects
- **DB write:** `VillaRoomsPlacement`.
- **No outbound sync** — it's a local reference table; placement is denormalised into the room sync payload.

---

## Bulk import rooms from CSV / Excel

**ID:** `CATALOG.ROOM.BULK_IMPORT`
**Trigger:** File upload on `BulkRoomsImport.razor`.
**Actor:** Property manager.
**Legacy locus:** `PropertyService2.cs:1009-1030` (`BulkRoomUpload`).

### Inputs
A `DataTable` whose columns map to: `Name`, `VillaId`, `WebsiteDescription`, `VCNotes`, `BedDouble`, `BedTwinDouble`, `BedTwin`, `BedSingle`, `BedBunk`, `BedSofa`, `BedChildrens`, `IsEnsuit`.

### Process
1. Map columns via a `Tuple<string,string>` list.
2. `BulkInsertAsync(table, "VillaRooms", _data_)` — SqlBulkCopy or equivalent.
3. Per-row errors captured by marking `row.RowError = "Fail"` and appending to a warning column.

### Outputs / side effects
- **DB write:** many `VillaRooms` rows in a single batch.
- **No `PlacementId`** in the import — rows arrive without placement and require subsequent manual assignment.
- **No sync triggered** on import — sync would need a manual trigger after.

### Failure modes
- FK on `VillaId` invalid → row marked Fail.
- Bed count parse fails → row marked Fail.
- File parse error → returns `false` at method level.

### Open questions
- Bulk import that skips placement and skips sync is a half-feature. Redesign should validate, transactionally commit, and queue a single sync push.
