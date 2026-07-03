# Property Features

Assigning amenity tags to a property. The features themselves are managed in `02-administration/product-taxonomy.md`. This file covers the **per-property** assignment.

## Assign / update / remove feature on a property

**ID:** `CATALOG.PROPERTY_FEATURE.UPSERT`, `CATALOG.PROPERTY_FEATURE.DELETE`
**Trigger:** Save on `PropertyFeaturesContent.razor`, organised by feature category.
**Actor:** Property manager.
**Legacy locus:** `PropertyService2.cs:466-518` (`GetUpdatePropertyFeaturesTagsByCategoryDetailsAsync`); SP `SP_CRUD_VILLA_FEATURES_TAGS`.

### Inputs
- `VillaId`
- `CategoryId` (which feature category we're editing — collections, indoor, outdoor, service-included, service-on-request, etc.)
- `SelectedFeatures` (List<feature objects>) on bulk INSERT
- `FeatureId` (single feature) on UPDATE / DELETE
- `Description` (per-property override text — e.g., "Heated pool, 8m × 3m")
- `Order`
- `Id` (assignment row id, 0 for INSERT)
- `Action`

### Process
1. **Special case CategoryId == 80 (Collections)**: for each selected feature, also writes a row to the collection-mapping path via `_resService.GetVillaByCollectionId(collectionObj)` (`PropertyService2.cs:480`). This is the back-channel that maintains `VillaCollectionsMappings` alongside the feature-tag row.
2. For INSERT, iterate `SelectedFeatures`: per feature, build parameter set (`Action`, `Id=0`, `FeatureId`, `VillaId`, `Order`, `CategoryId`, `Description`) and execute SP.
3. For UPDATE / DELETE on a single feature: execute SP with single `FeatureId`.

### Outputs / side effects
- **DB write:** `VillaFeaturesTags` rows.
- **Side write (when category 80):** `VillaCollectionsMappings` rows via the collection sub-call.
- **No direct sync queue entry**; downstream Villa Features sync (`INTEGRATIONS.PUBLIC_API.VILLA_FEATURE_SYNC`) is triggered separately, typically during a property save.

### Failure modes
- `VillaId <= 0` → SP fails silently.
- Empty `SelectedFeatures` → no INSERTs run; returns existing list.

### Open questions
- The "category 80 = collections" magic number is opaque and the back-channel mutation of `VillaCollectionsMappings` from a "feature" workflow is confusing. Untangle in the redesign: features and collection-membership are separate concerns.

---

## Send booking-confirmation email to a property contact

**ID:** `CATALOG.PROPERTY_CONTACT.SEND_CONFIRM_EMAIL`
**Trigger:** Auto-trigger from the booking confirm workflow, or staff "send confirmation" action against a contact mapping row.
**Actor:** Staff / system.
**Legacy locus:** `PropertyService.cs:1481-1500` (`SentBookingConfirmEmail`).

### Inputs
- `VillaContactMapping` (the property↔contact mapping row), specifically `Email`.

### Process
1. Build `EmailConfig`:
   - `Module = "enquire_auto_replay_email"` `[TYPO]` (intended `enquire_auto_reply_email`)
   - `To.Add(args.Email)`
   - `Subject = "Thank You for Your Enquiry – We'll Get Back to You Soon"`
2. `EmailService.SentEmail(emailConfig)`.

### Outputs / side effects
- **Email out** via the global SMTP profile.
- **No DB write** in this workflow — caller is expected to also persist the `IsCC`/flagged state.

### Failure modes
- Empty email → caught by caller validation; otherwise the SMTP send raises.

### Open questions
- The "auto reply" template module name is a leftover from the enquiry flow being repurposed for booking confirmation. Add a proper `BOOKING_CONFIRMATION` template.
- The mapping between this workflow and `BOOKING.LIFECYCLE.OWNER_CONFIRM` (in `09-booking/booking-confirmation.md`) is unclear — the latter sends its own email. Decide which is authoritative.
