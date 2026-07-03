# Public Website (Res API) Sync

The public villacollective.com WordPress site is the customer-facing front. The back-office Res system pushes property data, booking confirmations, and payment-schedule updates to it via a set of `WP_Sync_*` REST endpoints. Multi-tenancy is real: pushes are **grouped by `SiteId`** and dispatched to each configured `VillaConfigWebsite` row in turn.

## External ID continuity (critical for data migration)

The WP integration is **multi-tenant**: every villa, booking, and concierge entry can be published to multiple WordPress sites, each issuing its own post id and URL slug. The legacy system stores this in two places:

1. **`VillaSyncDetail`** — the normalised, per-(site, module, primary-id) sync table. Carries `SyncId` (WP post id) and `VillaUrl` (slug) for every successful push. **This is the authoritative source for WP external-id migration.**
2. **`VillaMaster.Slug` / `VillaBooking.BookingUrl` / `VIllaConcierges.Slug`** — convenience denormalisations of the most-recent push's slug, written inline by `PushVillaBookingToWP`, `PushConciergeBookingToWP`, and `sp_getSyncVilla`. These cover only the single most recently synced site, **not** the full fan-out.

### What must migrate

| Legacy source | New target |
|---|---|
| Each `VillaSyncDetail` row | `SyncRecord(provider=WORDPRESS_SITE, provider_instance=<SiteId>, content_type=<from ModuleId>, object_id=<from ModulePrimaryId>, external_id=<SyncId>, external_url=<VillaUrl>)` |
| `VillaBooking.BookingUrl` (where no `VillaSyncDetail` row exists) | Same shape, with `external_url=BookingUrl` and `external_id=""` (the legacy code stores only the URL for bookings). Capture the `SiteId` from `VillaConfigWebsite` — typically `SiteId=1` is the canonical public site. |
| `VIllaConcierges.Slug` (same gap) | Same shape, `external_url=Slug`. |

See `08-integrations.md` → "Migrating legacy external IDs" for the loader spec and the column-to-record mapping.

### Why this matters

- **`Import_Booking` is not idempotent without a recognisable post id on the WP side.** If the new system re-pushes a booking that already has a WP page, but no `SyncRecord(provider=WORDPRESS_SITE, …, external_id=…)` is present, WordPress allocates a fresh post; the public booking-confirmation URL changes; previously-emailed guest links 404.
- **The villa post-id (`PostId`) controls which WP post the next `WP_Sync_Villa` call updates.** Drop it and every villa double-publishes on first sync.
- **Each site is independent.** Migration must preserve every `(villa, site)` pair from `VillaSyncDetail`, not just the most-recently-touched one. A naive migration that only copies `VillaMaster.Slug` will lose every secondary-site link.

### Stop-the-bleeding posture at cutover

Until the WP external-id migration passes the `reconcile_legacy` extension (counts in legacy `VillaSyncDetail` match counts in new `SyncRecord` per `provider_instance`), keep all WP push tasks paused. The blast radius of an accidental duplicate-publish is larger than Zoho's because the URLs are public and customer-facing.

## WordPress-exclusive content fields

The Res → WP sync is **one-way** — Res pushes, WP consumes — but the public site holds editorial content that is **not** mirrored in Res. Per the 2026-05-26 scoping session with the site owner, this is the current shape and the rebuild does not flip it.

Examples of fields that live only on the WordPress side:

- Hero image cropping / focal point (Res sends the image; WP picks the focal point).
- SEO title and meta description (set per-villa in the WP page editor).
- Long-form editorial content layered on top of the Res `PropertyDescription` (`OVERVIEW` / `HOUSE_RULES` / `VILLA_INFO` / `FURTHER_INFO`) — WP is allowed to extend.
- Page-level marketing widgets (testimonials, related-villa carousels, callouts).
- Collection landing-page editorial copy beyond the `Collection.description` field.

The implications for the rebuild:

1. **A `WP_Sync_Villa` push must not overwrite WP-exclusive fields.** The WP-side plugin handles the merge — Res sends only the fields it owns, and the WP plugin updates only those columns on the WP post. Confirm this contract on a per-endpoint basis when the WP plugin source is reached (see "Response-shape gap" below).
2. **Res is not authoritative for editorial content.** Operators editing a villa in Res should see only the fields Res controls; they should not be surprised when their WP-side editorial copy survives a Res-side update.
3. **Flipping Res to be authoritative for editorial content is not in scope.** It would require pulling WP fields into Res, building editorial UI in the operator app, and shutting down WP-side editing — a meaningfully larger project than the rebuild. Recorded as out-of-scope.

If WP-side fields ever need to be visible inside Res (for example, an operator wanting to know what hero image is being shown on the public site), the surface is a read-only mirror: a nightly pull task that populates `SyncRecord.meta["wp_view"]` with a snapshot of the WP-rendered values. No editing of those values from inside Res.

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

### Idempotency
- **Not idempotent and not resumable.** The sequence is run inline by one HTTP request handler with no per-step persisted state — if step 7 fails, steps 1-6 have already run (and may have written back slug / post-id state to local rows) and there is no marker to skip them on a re-run. A retry re-pushes every record.
- The Django redesign should fan this out into 13 × N (modules × sites) Celery tasks, each keyed by `(SyncRecord.kind, target_id, site_id)`. The orchestration becomes an idempotent "ensure every (kind, target, site) has a successful SyncRecord within the last N hours" loop, not a fragile linear sequence.

### Failure modes
- Any step's failure is logged but does not abort the sequence.
- No partial-resync mode — must run the whole thing.

### Response-shape gap

Of the 13 sub-workflows above, only the per-villa `VILLA_SYNC` (`PostId` + `Url` write-back) and `BOOKING_IMPORT` (`Data.Url` + `Data.BookingId` write-back) have a documented response shape. The other 11 read the response as `Response` with no documented field expectations; treat the response as "any 2xx is success" until the WordPress endpoints are inspected directly.

The Django port must:
1. For each `WP_Sync_*` endpoint, capture the WordPress-side handler signature in `workflows/11-integrations/public-website-sync.md` next to the sub-workflow.
2. Define a typed `pydantic` response model per endpoint so unexpected shapes raise rather than silently succeed.
3. Treat any endpoint where the response shape is unknown as **opaque** — store the raw body in `WebhookDelivery.response_payload` for at least 30 days so an operator can reconstruct what WordPress was returning.

### Open questions
- Idempotent, retryable per-module Celery tasks (one task per `(module, site)` pair) replace this sequence cleanly.
- Add progress reporting and per-module success / failure metrics.
- Owner of the WordPress-side endpoint schemas — confirm whether the WP plugin source is reachable from this repo.
