# Property Imagery

Property images are uploaded to disk and indexed by `VillaPropertyImages`. Each image carries role flags (`IsHero`, `IsInterior1`, `IsInterior2`, `IsExterior1`, `IsExterior2`, `IsGallary` `[TYPO]`) plus a `SortOrder` and `GallaryOrder`. A sibling table `VillaPropertyImagesDescription` holds long-form site content keyed by villa.

## Upload property image

**ID:** `CATALOG.IMAGE.UPLOAD`
**Trigger:** File selection on `PropertyImageUpload.razor`.
**Actor:** Property manager.
**Legacy locus:** `PropertyService2.cs:674-720` (`SaveVillaPropertyImages`); SP `SP_Insert_VillaPropertyImages`.

### Inputs
- `VillaId` (required, > 0)
- `Name` (filename)
- `Description` (caption)
- Role flags: `IsGallary`, `IsHero`, `IsInterior1`, `IsInterior2`, `IsExterior1`, `IsExterior2`
- Underlying file binary (uploaded separately)

### Process
1. File saved to disk path: `https://vc2.mojodev.co.uk/PropertyImages/{VillaId}/{filename}` — the URL is hardcoded in `PropertyService2.cs:766`.
2. `VillaId > 0` check.
3. Build 9 parameters, execute `SP_Insert_VillaPropertyImages`. Returns new image `Id`.
4. `WPSaveAsyns({image_name=filename}, villaId, userName, INSERT)` — async, non-blocking call to WordPress.

### Outputs / side effects
- **File system write:** image saved (storage mechanism not in committed code).
- **DB write:** `VillaPropertyImages` row.
- **Outbound push:** `INTEGRATIONS.PUBLIC_API.VILLA_IMAGE_SINGLE_SAVE`.

### Data transformations for storage
- Filename preserved as-is — no sanitisation visible (`[SECURITY]` traversal risk).
- Image role flags stored as bits.

### Failure modes
- `VillaId <= 0` → "Fail to upload image".
- Disk write failure → exception caught → "Fail to upload image".
- WordPress sync timeout → async log, doesn't fail the upload.

### Open questions
- Hardcoded `vc2.mojodev.co.uk` is a dev-environment URL leaking into production. Use Django `FileField` + storage backend.
- Filename sanitisation must be added.

---

## Toggle image role flags

**ID:** `CATALOG.IMAGE.UPDATE_OPTIONS`
**Trigger:** User toggles Hero / Interior / Exterior badges on an image card.
**Actor:** Property manager.
**Legacy locus:** `PropertyService2.cs:839-869` (`UpdateVillaPropertyImagesOptions`); SP `SP_UPDATE_VILLAPROPERTYIMAGES_OPTIONS`.

### Inputs
- `Id`, `VillaId`
- Role flags: `IsHero`, `IsInterior1`, `IsInterior2`, `IsExterior1`, `IsExterior2` (and `IsGallary`)
- `User`

### Process
1. Execute SP with all flags.
2. Queue sync: `UpdateSyncId(VILLA_IMAGES, VillaId, 0, 0, UPDATE)`; call `VillaImagesSync`.

### Outputs / side effects
- **DB write:** `VillaPropertyImages` flag columns + `IsSynced=0`.

---

## Reorder images

**ID:** `CATALOG.IMAGE.REORDER`
**Trigger:** Drag-drop in gallery / arrow buttons.
**Actor:** Property manager.
**Legacy locus:** `PropertyService2.cs:885-905` (`UpdateSortOrderNo`).

### Inputs
- `Id`, `Propertyid`, target sort index `target`, source index `source`, `user`, `type`.

### Process
1. Raw SQL: `UPDATE VillaPropertyImages SET IsSynced=0, SortOrder = {target} WHERE VillaId={Propertyid} AND Id={id}`. **One UPDATE per moved image** — N round-trips for one drag.
2. `_apiService.VillaImagesSync(...)`.

### Outputs / side effects
- **DB write:** single-row SortOrder update; only the dragged image's row changes (other rows are inferred to shift via UI-side recalculation that the legacy code doesn't show — this is a smell).
- **Outbound push:** images sync.

### Failure modes
- **SQL injection risk** `[SECURITY]` — values are `int`s at the call site but the pattern is raw string concatenation.
- Reorder atomicity is unclear; concurrent reorders could leave gaps/dupes in `SortOrder`.

### Open questions
- Use `django-ordered-model` or a single ranked-list re-shuffle.

---

## Edit image description

**ID:** `CATALOG.IMAGE.UPDATE_DESCRIPTION`
**Trigger:** Modal save on image-edit panel.
**Actor:** Property manager.
**Legacy locus:** `PropertyService2.cs:920-940`; SP `SP_CRUD_VILLAPROPERTYIMAGES` with `@Action=UPDATE_DESCRIPTION`.

### Inputs
- `Id`, `VillaId`, `Description`

### Process
1. Execute SP with `UPDATE_DESCRIPTION` action.
2. **No sync queue entry** — description-only edit does not push.

### Open questions
- Inconsistency: description edits do not push to WordPress, but option toggles do. Decide one rule and apply consistently.

---

## Set image site descriptions (long-form web content)

**ID:** `CATALOG.IMAGE.UPDATE_SITE_DESCRIPTIONS`
**Trigger:** Save on `ImageDescription.razor`.
**Actor:** Content manager.
**Legacy locus:** `PropertyService2.cs:955-991`; SP `SP_CRUD_VILLAPROPERTYIMAGESDESCRIPTION`.

### Inputs
- `VillaId`
- Six content blocks: `WebDesc1`, `WebDesc2`, `Interior1`, `Interior2`, `Exterior1`, `Exterior2`, `Location1`, `Location2`
- `VodeoUrl` `[TYPO]` (intended `VideoUrl`)
- `UserId`

### Process
1. Build parameters, execute SP.
2. On affected rows: `UpdateSyncId(VILLA_DESCRIPTION, VillaId, 0, UserId, action)` and `VillaDescriptionSync(VillaId)`.

### Outputs / side effects
- **DB write:** `VillaPropertyImagesDescription`.
- **Outbound push:** `INTEGRATIONS.PUBLIC_API.VILLA_DESCRIPTION_SYNC`.

### Open questions
- Fixed slot model is rigid. Replace with rich `PropertyContent` (or named-block content type) in the redesign.
- `VodeoUrl` typo to fix.

---

## Bulk import image descriptions

**ID:** `CATALOG.IMAGE.BULK_IMPORT_DESCRIPTIONS`
**Trigger:** File upload on `BulkImportTextImage.razor`.
**Actor:** Content manager.
**Legacy locus:** `PropertyService2.cs:1038-1075` (`BulkImportImageAndText`); SP `SP_BulkImport_VillaPropertyText`.

### Inputs
- `DataTable` with columns: `Property Id`, `Web Des 1`, `Web Des 2`, `Interior Sub`, `Interior Para`, `Exterior Sub`, `Exterior Para`, `Location Sub`, `Location Para`.

### Process
1. Iterate rows; per row, execute the SP with 10 parameters.
2. Per-row error capture (`row.RowError = "Fail"`).

### Outputs / side effects
- **DB write:** many rows in `VillaPropertyImagesDescription`.
- **No sync triggered.**

### Failure modes
- FK on VillaId invalid → row Fail.
- Returns `true` even if all rows fail — failures are only visible in the row warning column.

---

## Delete image(s)

**ID:** `CATALOG.IMAGE.DELETE`, `CATALOG.IMAGE.DELETE_ALL`
**Trigger:** Trash icon on image card; "Delete All" action on the gallery.
**Actor:** Property manager.
**Legacy locus:** `PropertyService2.cs:795-825` (`DeleteVillaPropertyImagesAsync`); SP `SP_CRUD_VILLAPROPERTYIMAGES`.

### Inputs
- `Id`, `VillaId`
- `deleteType` (-1 = all-for-property, else single)

### Process
1. Build parameters; insert `@Action=DELETE` or `DELETEALL`.
2. Execute SP.
3. `PushOrderImageToWP(villaId, user, isDeleteAll=false)`:
   - `UpdateSyncId(VILLA_IMAGES, villaId, 0, 0, UPDATE)`
   - `_apiService.VillaImagesSync(..., isDeleteAll)`.

### Outputs / side effects
- **DB write:** rows deleted from `VillaPropertyImages` (likely soft via `IsSynced=0` flag — confirm in SP).
- **Outbound push:** images sync with `isDeleteAll` flag.

### Failure modes
- `VillaId <= 0` → "Fail to load image".

### Open questions
- The on-disk file is **not** deleted by this workflow (no file-system action in code). Files orphan over time. Add a cleanup task.
