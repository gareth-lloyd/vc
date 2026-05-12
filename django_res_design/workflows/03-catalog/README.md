# 03 · Catalog

Property (villa) master data and the workflows that produce, edit, and publish it. This domain holds the largest tables in the legacy system — `VillaMaster` and `VillaFinance` are "god objects" with many tens of columns each. The Django redesign splits them; the workflows below still target the legacy aggregate names so the migration is traceable.

## Files

| File | Workflows |
|---|---|
| [`property-master.md`](./property-master.md) | Save property overview, set website status, configure settings (check-in/out times, currency, change-over day, min nights, pricing-entered mode, booking-approval flag) |
| [`property-rooms.md`](./property-rooms.md) | Define / update / delete rooms, manage room placements (Ground/First/etc.), bulk import rooms from CSV/Excel |
| [`property-imagery.md`](./property-imagery.md) | Upload image, reorder images, edit image description, set image site descriptions (long-form content), bulk import descriptions, delete image(s) |
| [`property-features.md`](./property-features.md) | Assign features/amenities to a property, manage feature-categories, send booking-confirmation email to property contact |
| [`property-nearby.md`](./property-nearby.md) | Add / edit / delete nearby points-of-interest (restaurants, beaches, etc.) with distance and access methods |
| [`property-finance.md`](./property-finance.md) | Configure tax, commission, bank account, payment schedule, security deposit policy on a property (all five concerns multiplexed through one SP today) |

## Entities touched

- `VillaMaster` — master record (~50 columns)
- `VillaFinance` — finance god-object (commission, tax, bank, payment schedule, security deposit)
- `VillaSettings` — operational settings (check-in/out, min nights, change-over, currency)
- `VillaRooms`, `VillaRoomsPlacement` — rooms hierarchy
- `VillaPropertyImages`, `VillaPropertyImagesDescription` — imagery + content
- `VillaFeaturesTags` — junction property↔feature (with description + order)
- `VillaPropertyNearBy` — POIs
- `VillaContactMapping` — property↔contact (covered in `05-directory/`)

## Sync modules (push to WordPress public site)

| Module | Endpoint | Triggered by |
|---|---|---|
| `ResModule.VILLA` | `/WP_Sync_Villa` (full villa record) | property overview save, status change |
| `ResModule.VILLA_ROOMS` | `/WP_Sync_Villa` (rooms variant) | room save |
| `ResModule.VILLA_IMAGES` | `/WP_Sync_Villa` (images variant) | image upload / reorder / option-toggle / delete |
| `ResModule.VILLA_DESCRIPTION` | `/WP_Sync_Villa` (description variant) | site-descriptions save |
| `ResModule.VILLA_LOCATION` | `/WP_Sync_Villa` (nearby variant) | nearby POI save |

A property's "site status" is pushed in the `VILLA_DETAILS` variant of the villa sync.

## Open design questions for the Django redesign

- **Decompose `VillaMaster`** into focused models per concern (overview / location / capacity / settings) joined OneToOne. The `../02-properties.md` design already plans this.
- **Decompose `VillaFinance`** into five FK-attached models (Commission, Tax, BankAccount, PaymentSchedule, SecurityDepositPolicy). The `../03-finance-config.md` design already plans this with `null-means-inherit` semantics replacing the `IsDefaultSetting*` flag pairs.
- **Image storage** in legacy is to a hardcoded URL pattern `https://vc2.mojodev.co.uk/PropertyImages/{VillaId}/{filename}`. Redesign should use Django's `FileField` with a storage backend (S3 / Cloud Storage).
- **Bulk imports** are per-row SP calls with `RowError = "Fail"` strings — replace with proper validation + transactional CSV import.
- **Site descriptions** ("Web Des 1", "Interior Para", etc.) are a fixed slot-based content model. Redesign as a richer `PropertyContent` with named blocks or use a CMS-style structure.
