# Public Website (Res API) Sync

The public villacollective.com WordPress site is the customer-facing front. The back-office Res system pushes property data, booking confirmations, and payment-schedule updates to it via a set of `WP_Sync_*` REST endpoints. Multi-tenancy is real: pushes are **grouped by `SiteId`** and dispatched to each configured `VillaConfigWebsite` row in turn.

Each sync workflow follows the same broad shape:
1. Read pending rows from `SP_GET_SYNC_DATA_BY_MODULE(@module, @action, @id)`.
2. Group by `SiteId`.
3. Per site, build a JSON payload and HTTP POST it to the site URL with a Bearer token.
4. On success, update local sync state (often by writing back a slug or post id).

All endpoints accept POST. All use Bearer auth via `SyncProperties.ApiToken`.

## Country sync

**ID:** `INTEGRATIONS.PUBLIC_API.COUNTRY_SYNC`
**Endpoint:** `{site}/WP_Sync_Country`
**Legacy locus:** `ResApiService.cs:53-85`.

### Payload
```
{
  Countries: [ { CountryId, CountryName, is_Enable } ],
  DeleteCountries: [ ... ]
}
```

### Triggered by
`ADMIN.GEO.COUNTRY_UPSERT` / `_REORDER`, `MANUAL_FULL_SYNC`.

---

## Region sync

**ID:** `INTEGRATIONS.PUBLIC_API.REGION_SYNC`
**Endpoint:** `{site}/WP_Sync_Regions`
**Legacy locus:** `ResApiService.cs:107-139`.

### Payload
```
{ Regions: [ { CountryId, RegionId, RagionName[TYPO], DeletedBy } ], DeleteRegions: [ ... ] }
```

### Triggered by
`ADMIN.GEO.REGION_UPSERT`, `MANUAL_FULL_SYNC`.

---

## Feature sync (vocabulary)

**ID:** `INTEGRATIONS.PUBLIC_API.FEATURE_SYNC`
**Endpoint:** `{site}/Sync_key_feature`
**Legacy locus:** `ResApiService.cs:209-239`.

### Payload
```
{ Features: [ { Id, Name, Description, Category, FeatureOrder } ], DeleteFeatures: [ ... ] }
```

### Triggered by
`ADMIN.TAXONOMY.FEATURE_UPSERT` / `_REORDER`, `MANUAL_FULL_SYNC`.

---

## Collection sync

**ID:** `INTEGRATIONS.PUBLIC_API.COLLECTION_SYNC`
**Endpoint:** `{site}/WP_Sync_Collections`
**Legacy locus:** `ResApiService.cs:143-173`.

### Payload
```
{ Collections: [ { Id, Text } ], DeleteCollections: [ ... ] }
```

### Triggered by
`ADMIN.TAXONOMY.COLLECTION_UPSERT`, `MANUAL_FULL_SYNC`.

---

## Villa sync (full property record)

**ID:** `INTEGRATIONS.PUBLIC_API.VILLA_SYNC`
**Endpoint:** `{site}/WP_Sync_Villa`
**Legacy locus:** `ResApiService.cs:241-315`.

### Payload
Dynamic object returned by `sp_getSyncVilla` — captures every villa field. Includes:
- `PropertyId`, `Name`, `VillaStatus`, `Action` (e.g., `"INSERT_FIELD"`, `"STATUS_DETAILS"`, `"VILLA_DETAILS"`)
- Plus the full set of overview / location / capacity columns

### Response handling
- If response has `PostId` + `Url`, persist via `sp_getSyncVilla @Action=UPDATE @SyncAction='' @Id={id} @Slug={url} @SyncId={postId}` — writes back the WordPress post id and URL slug to local villa.

### Triggered by
`CATALOG.PROPERTY.UPDATE_OVERVIEW`, `CATALOG.PROPERTY.SET_WEBSITE_STATUS`, `MANUAL_FULL_SYNC`.

---

## Villa rooms sync

**ID:** `INTEGRATIONS.PUBLIC_API.VILLA_ROOMS_SYNC`
**Endpoint:** `{site}/WP_Sync_Villa` (rooms variant — discriminated by `Action="{op}_FIELD"`)
**Legacy locus:** `ResApiService.cs:358-398`.

### Payload
```
{
  PropertyId, Name, VillaStatus,
  Action: "INSERT_FIELD" | "UPDATE_FIELD" | "DELETE_FIELD",
  RoomDetails: [ { Placement, RoomDetailId, Name, Description, IsActive } ]
}
```

### Triggered by
`CATALOG.ROOM.UPSERT`, `MANUAL_FULL_SYNC`.

---

## Villa features sync (per-property amenities)

**ID:** `INTEGRATIONS.PUBLIC_API.VILLA_FEATURE_SYNC`
**Endpoint:** `{site}/WP_Sync_Villa` (features variant)
**Legacy locus:** `ResApiService.cs:439-495`.

### Payload
Dynamic object with category-bucketed feature arrays:
- `IncludedFeatures` (from category `ServiceIncluded`)
- `IndoorFeatures`, `IndoorFeaturesData`
- `OutdoorFeatures`, `OutdoorFeaturesData`
- `ServiceOnRequest`
- `KeyFeatures` (comma-separated active-feature names)

Plus `PropertyId`, `Name`, `VillaStatus`, `Action`.

### Triggered by
`MANUAL_FULL_SYNC` (per-property feature workflow doesn't directly push — fires only via full sync).

---

## Villa nearby sync

**ID:** `INTEGRATIONS.PUBLIC_API.VILLA_NEARBY_SYNC`
**Endpoint:** `{site}/WP_Sync_Villa` (nearby variant)
**Legacy locus:** `ResApiService.cs:497-545`.

### Payload
```
{
  PropertyId, Name, VillaStatus, Action: "{op}_FIELD",
  NearByData: [ { Id, Distance, CategoryType, Name, Description, ByWalk, ByDrive, ByBoat, IsActive } ]
}
```

### Triggered by
`CATALOG.PROPERTY_NEARBY.UPSERT`, `MANUAL_FULL_SYNC`.

---

## Villa images sync (bulk)

**ID:** `INTEGRATIONS.PUBLIC_API.VILLA_IMAGES_SYNC`
**Endpoint:** `{site}/WP_Sync_Villa` (images variant)
**Legacy locus:** `ResApiService.cs:547-634`.

### Payload
```
{
  PropertyId, Name, VillaStatus, Action,
  PropertyImage:    [ ... (hero) ],
  InteriorImages:   [ ... ],
  ExteriorImages:   [ ... ],
  Galaries:         [ ... ] [TYPO],
  GridImages:       [ ... ]
}
```

Images are bucketed by role flags from `VillaPropertyImages`.

### Triggered by
`CATALOG.IMAGE.UPDATE_OPTIONS`, `CATALOG.IMAGE.REORDER`, `CATALOG.IMAGE.DELETE`, `MANUAL_FULL_SYNC`.

---

## Villa image single save / delete

**ID:** `INTEGRATIONS.PUBLIC_API.VILLA_IMAGE_SINGLE_SAVE`
**Endpoint:** `{site}/villa_id/{id}` (INSERT) or `{site}/delete/image_delete/{id}` / `{site}/delete/villa_id/{id}` (DELETE)
**Legacy locus:** `ResApiService.cs:668-685` (`VillaSaveImageAsyns`).

### Triggered by
`CATALOG.IMAGE.UPLOAD` (single-image fire-and-forget).

---

## Villa description sync

**ID:** `INTEGRATIONS.PUBLIC_API.VILLA_DESCRIPTION_SYNC`
**Endpoint:** `{site}/WP_Sync_Villa` (description variant)
**Legacy locus:** `ResApiService.cs:636-666`.

### Triggered by
`CATALOG.IMAGE.UPDATE_SITE_DESCRIPTIONS`, `MANUAL_FULL_SYNC`.

---

## Villa alternative-rental sync

**ID:** `INTEGRATIONS.PUBLIC_API.VILLA_ALTERNATIVE_RENTAL_SYNC`
**Endpoint:** `{site}/WP_Sync_Villa` (alternative variant)
**Legacy locus:** `ResApiService.cs:317-356`.

### Two flavours (discriminated by `Data` int):
- `Data=10`: `PupularProperties` `[TYPO]` (intended "Popular") — "you might also like" suggestions
- `Data=20`: `RentToGatherData` `[TYPO]` (intended "RentTogether") — adjacent properties that can be rented as a group

### Payload (Data=10)
```
{ PropertyId, Name, VillaStatus, Action: "{op}_FIELD",
  PupularProperties: [ { PropertyId, IsActive } ] }
```

### Payload (Data=20)
```
{ PropertyId, Name, VillaStatus, Action: "{op}_FIELD",
  RentToGatherData: [ { PropertyId, IsActive } ] }
```

### Triggered by
`MANUAL_FULL_SYNC`.

---

## Booking import push

**ID:** `INTEGRATIONS.PUBLIC_API.BOOKING_IMPORT`
**Endpoint:** `{site}/Import_Booking`
**Legacy locus:** `ResApiService.cs:737-769` (`PushVillaBookingToWP`).

### Payload
Full booking object including personal info, payment schedule, villa details.

### Response handling
- Response carries `Data.Url` (the WordPress booking-display URL) and `Data.BookingId`. The Url is persisted: `UPDATE VillaBooking SET BookingUrl='{url}' WHERE Id={id}`.

### Triggered by
`BOOKING.LIFECYCLE.CREATE_FROM_QUOTATION`.

---

## Concierge service push

**ID:** `INTEGRATIONS.PUBLIC_API.CONCIERGE_SYNC`
**Endpoint:** `{site}/ConciergeServiceBooking`
**Legacy locus:** `ResApiService.cs:771-803` (`PushConciergeBookingToWP`).

### Response handling
- Stored slug: `UPDATE VIllaConcierges` `[TYPO]` `SET Slug='{url}' WHERE Id={id}`.

### Triggered by
`BOOKING.CONCIERGE.SAVE`.

---

## Payment dues / checkout data push

**ID:** `INTEGRATIONS.PUBLIC_API.PAYMENT_DUES_PUSH`, `INTEGRATIONS.PUBLIC_API.FLYWIRE_CHECKOUT_DATA_PUSH`
**Endpoint:** `{site}/PaymentDuesDates` (also reached via `/Import_Booking` in some paths)
**Legacy locus:** `ResApiService.cs:805-837`, `:1059-1071`.

### Payload
```
{ bookingId, PaymentDuesDates: [ { Id, Description, Amount, Date, IsPayment } ] }
```

### Triggered by
`PAYMENT.COLLECTION.WEBHOOK_RECEIVE` (on `status=guaranteed`).

---

## Full sync orchestration

**ID:** `INTEGRATIONS.PUBLIC_API.FULL_SYNC_ORCHESTRATION`
**Trigger:** "Sync" button on `/config` (`ADMIN.SYSCONFIG.MANUAL_FULL_SYNC`) or system startup.
**Actor:** Admin / system.
**Legacy locus:** `ResApiService.cs:687-735` (`StartResSyncProcess`).

### Process (sequential, no retry)
1. `CountrySync(UPDATE)`
2. `RegionSync(UPDATE)`
3. `CollectionsSync(UPDATE)`
4. `FeatureSync(SYNC)`
5. `VillaSync(SYNC)` — full villa records
6. `VillaAlternativeRentalSync(Data=10)`
7. `VillaAlternativeRentalSync(Data=20)`
8. `VillaRoomsSync(INSERT)`
9. `VillaFeatureSync(SYNC)`
10. `CollectionVillaSync(SYNC)`
11. `VillaNearByAsync(SYNC)`
12. `VillaImagesSync(SYNC)`
13. `VillaDescriptionSync()`

### Outputs / side effects
- All property data mirrored to every configured WordPress site.
- Full log of request/response per call.
- Returns boolean success.

### Failure modes
- Any step's failure is logged but does not abort the sequence.
- No partial-resync mode — must run the whole thing.

### Open questions
- Idempotent, retryable per-module Celery tasks (one task per `(module, site)` pair) replace this sequence cleanly.
- Add progress reporting and per-module success / failure metrics.
