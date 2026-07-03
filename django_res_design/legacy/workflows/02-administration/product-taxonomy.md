# Product Taxonomy

Collections (curated marketing groupings of villas), Groups (ownership / legal groupings), Tags / Features (amenity vocabulary), and the villa-to-collection mapping. Collections and Groups share a backing table (`VillaGroup`) `[TYPO]` of intent — they should be separate.

## Manage collections (CRUD)

**ID:** `ADMIN.TAXONOMY.COLLECTION_UPSERT`, `ADMIN.TAXONOMY.COLLECTION_DELETE`
**Trigger:** Admin actions on `/collection/new` (`Pages/Others/Collections.razor`).
**Actor:** Admin.
**Legacy locus:** `Collections.razor`; SP `sp_villa_groups`.

### Inputs
- `Id` (0 for INSERT)
- `Name` (required, unique within "collection" usage)
- `Description` (HTML allowed — rendered with read-more on the admin list)

### Process
1. Uniqueness pre-check → `"Collections {Name} is already exist in the res system!"`.
2. `sp_villa_groups` with `@Action` (collection-discriminated by code path — the table is shared).
3. Sync queue: `UpdateSyncId(40, id, 0, userId, UPDATE)` then `_apiService.CollectionsSync(SyncPostData)`.

### Outputs / side effects
- **DB write:** `VillaGroup` row (collection variant).
- **Sync queue:** module `40`.
- **Outbound push:** see `INTEGRATIONS.PUBLIC_API.COLLECTION_SYNC`.

### Open questions
- `VillaGroup` carries both collections and groups. Split in Django: `properties.Collection` and `properties.OwnerGroup` (or similar).

---

## Manage groups (CRUD)

**ID:** `ADMIN.TAXONOMY.GROUP_UPSERT`, `ADMIN.TAXONOMY.GROUP_DELETE`
**Trigger:** Admin actions on `/groups` (`Pages/Others/Groups.razor`).
**Actor:** Admin.
**Legacy locus:** `Groups.razor`; SP `sp_villa_groups` (different code path, same table).

### Inputs
- `Id`
- `Name` (required, unique within "group" usage)
- `Description`
- `IsActive` (bool)

### Process
Same CRUD pattern as collections. **No sync queue entry** — groups are local-only.

### Outputs / side effects
- **DB write:** `VillaGroup` row (group variant).
- **No outbound sync.**

### Open questions
- Same table-sharing concern as collections — split.

---

## Map villa(s) into a collection

**ID:** `ADMIN.TAXONOMY.COLLECTION_MAP_VILLAS`, `ADMIN.TAXONOMY.COLLECTION_UNMAP_VILLA`
**Trigger:** Admin selects a collection on `/collection/villa-map` (`Pages/Others/VillaCollectionMap.razor`), picks villas, clicks Save; or clicks the row trash icon to remove a single villa.
**Actor:** Admin.
**Legacy locus:** `VillaCollectionMap.razor:185-220` (add), `:89` (remove).

### Inputs
- `CollectionId` (int)
- `VillaIds` (string — comma-delimited from the multi-select)
- `Action` (`INSERT` for add, `DELETE` for remove)
- `User`

### Process
1. **Pre-check** for adds: iterate selected villas; for any already in the collection, surface error `"{villas} already exist in this collection!"` and skip them (`VillaCollectionMap.razor:189-198`).
2. `_resService.GetVillaByCollectionId(args)` (re-used name; this is the mapping mutation entry point) with the action.
3. Insert/delete rows in `VillaCollectionsMappings`.

### Outputs / side effects
- **DB write:** `VillaCollectionsMappings` rows.
- **No direct outbound sync** captured in code, but the collection-villas list is consumed by `INTEGRATIONS.PUBLIC_API.COLLECTION_VILLA_SYNC` in `StartResSyncProcess`.

### Data transformations for storage
- The `VillaIds` comma-delimited string is parsed and one row per villa inserted.

### Failure modes
- Add to non-existent collection → FK violation in SP.
- Duplicate (handled by pre-check).

### Open questions
- Pre-check + insert is racey. Single-statement INSERT with unique constraint and `ON CONFLICT DO NOTHING` is the Django pattern.

---

## Manage tags / features (CRUD + reorder)

**ID:** `ADMIN.TAXONOMY.FEATURE_UPSERT`, `ADMIN.TAXONOMY.FEATURE_DELETE`, `ADMIN.TAXONOMY.FEATURE_REORDER`
**Trigger:** Admin actions on `/tags` (`Pages/Others/Tags.razor`).
**Actor:** Admin.
**Legacy locus:** `Tags.razor`; SP `SP_CRUD_VILLA_FEATURES_TAGS`.

### Inputs
- `Id`
- `Name` (required)
- `Description`
- `ServiceType` (`10` = ContactService — used by directory/concierge, `20` = PropertyFeature — used by villa pages)
- `IconId`, `IconName` (refers to an embedded SVG sprite `#{IconName}` referenced as `/icon/icons__defs.svg#{IconName}`)
- `Categories` (List<int>) — multi-select; stored as comma-delimited `CategoryId`
- `Order` (int; managed via drag-drop reorder)
- `Action`

### Process
1. Validate: `Name` non-empty; at least one category selected (the UI error reads `"Please select Categeroy"` `[TYPO]`).
2. `SP_CRUD_VILLA_FEATURES_TAGS` with `@Action`, parameter set including `@CategoryId` (the comma-string).
3. Output param `@FeatureId`.
4. Feature-category mapping is updated as a secondary call (`SP_CRUD_VILLA_FEATURES_TAGS` with a category-mapping action) — error reads `"Tags categories not {action}"`.
5. Reorder: per-row loop pushing new `Order` (`Tags.razor:348-361`).
6. After save: `UpdateSyncId(ResModule.FEATURE, id, 0, userId, UPDATE)` and `_apiService.FeatureSync(SyncPostData)`; reorder additionally invokes `PushFeaturesToWP(userName)` (`Tags.razor:363`).

### Outputs / side effects
- **DB write:** `VillaFeatures` + `VillaFeaturesCategoryMapping` junction rows.
- **Sync queue:** `ResModule.FEATURE`.
- **Outbound push:** see `INTEGRATIONS.PUBLIC_API.FEATURE_SYNC`.

### Data transformations for storage
- Categories: UI multi-select → comma-delimited string (parsed on read). This is the typical legacy pattern; redesign should use a proper many-to-many junction.

### Open questions
- `ServiceType` is a small fixed enum (`10`/`20`) — model as a `TextChoices` in Django.
- Icon system referencing an external SVG sprite is fine; the redesign should store the icon `slug` (e.g., `"pool-icon"`) and resolve it client-side.
