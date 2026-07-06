# 02 — Properties

> **Design-time spec — frozen 2026-07-03.** Rationale for the design as
> conceived; not a live description of the built system. Current truth:
> [`../data-model-overview.md`](../data-model-overview.md) + the code in
> `django_res/` + [`../../todo/INDEX.md`](../../todo/INDEX.md).

The villa catalogue. Decomposes the legacy `VillaMaster` god object (~80 columns).

## File layout

```
properties/
├── enums.py
├── models/
│   ├── __init__.py
│   ├── geo.py          # Country, Region, NearbyPlace, NearbyPlaceType
│   ├── property.py     # Property, PropertyCategory
│   ├── location.py     # PropertyLocation
│   ├── capacity.py     # PropertyCapacity
│   ├── settings.py     # PropertySettings
│   ├── defaults.py     # PropertyDefaults (global creation-defaults singleton)
│   ├── descriptions.py # PropertyDescription
│   ├── rooms.py        # Room, RoomBeds
│   ├── images.py       # PropertyImage
│   ├── features.py     # Feature, FeatureCategory, Collection, CollectionMembership
│   └── contacts.py     # PropertyContactAssignment
```

(Finance models live in `03-finance-config.md`.)

## Geography

### `Country(TimestampedModel)`
- `name` — CharField
- `iso2`, `iso3` — CharField(2/3), unique
- `dial_code` — CharField (e.g. `+44`)
- `default_tax_rate` — Decimal(5,2)
- `sort_order` — int
- `is_active` — bool

### `Region(TimestampedModel)`
- `country` — FK Country, on_delete=PROTECT
- `name` — CharField
- `slug` — SlugField; `UniqueConstraint(country, slug)`
- `sort_order` — int
- `is_active` — bool

### `NearbyPlaceType(TimestampedModel)`
- `name` — CharField
- `icon` — CharField (icon class or asset key)

### `PropertyNearbyPlace(TimestampedModel)`
- `property` — FK Property CASCADE
- `place_type` — FK NearbyPlaceType PROTECT
- `name` — CharField (e.g. "Padstow Harbour")
- `distance_km` — DecimalField(6,2)
- `notes` — TextField(blank=True)
- `sort_order` — int

## Property core

### `PropertyCategory(TimestampedModel)`
Editable lookup (villa, apartment, chalet, lodge…).
- `name` — CharField, unique
- `slug` — SlugField
- `sort_order` — int

### `Property(AuditedModel)`
Thin aggregate root. Lifecycle is the explicit `status` enum below — no soft delete. Retiring a property uses `status=ARCHIVED`; reviewing the catalogue uses `?status=` filtering, never a hidden manager.
- `name` — CharField
- `display_name` — CharField
- `slug` — SlugField, unique
- `licence_number` — CharField(blank=True)
- `status` — `TextChoices` (`DRAFT`, `ACTIVE`, `ARCHIVED`) — three values only. `DRAFT` = work-in-progress, hidden from publish targets and search. `ACTIVE` = published, bookable, fanned out to integrations. `ARCHIVED` = retired (decommissioned, end-of-contract, sold). The legacy `live_offline` row collapses into `ARCHIVED`; operators reach the legacy "temporarily not bookable" effect by setting `PropertySettings.availability_default = UNAVAILABLE`, which is a separate axis. See reconciliation issue #23.
- `channel` — `TextChoices` (`DIRECT`, `AGENT`, `WHITE_LABEL`, `INTERNAL`)
- `category` — FK PropertyCategory PROTECT
- `region` — FK Region PROTECT
- `features` — M2M to `Feature` (no through; plain)
- `collections` — M2M to `Collection` through `CollectionMembership`
- `nearby_places` — reverse via `PropertyNearbyPlace`
- `legacy_id` — nullable, indexed

Indexes: `slug` (unique), `status`, `(region, status)`.

Default ordering: `["name", "id"]`. The `id` tiebreaker gives a **total** order so page-number pagination over `GET /properties` never duplicates or skips rows when two properties share a `name` — the quote builder pages through this listing (see `workflows/08-quotation/construction.md`).

## Decomposition models (OneToOne)

Each holds a distinct concern. OneToOne keeps the joins narrow and lets each form/admin inline target one concern.

### `PropertyLocation(AuditedModel)`
Owned by `Property` (CASCADE OneToOne) — no independent lifecycle. Hard-deleted with its parent.

- `property` — OneToOneField(Property, on_delete=CASCADE, primary_key=True)
- `address_line_1`, `address_line_2`, `address_line_3` — CharField(blank=True)
- `post_code` — CharField(blank=True)
- `locality_town` — CharField(blank=True)
- `locality_region` — CharField(blank=True)
- `country` — FK Country PROTECT
- `latitude` — DecimalField(9, 6, null=True, blank=True), validated to ±90
- `longitude` — DecimalField(9, 6, null=True, blank=True), validated to ±180
- `timezone` — CharField(max_length=64, default `"UTC"`), IANA name validated by `validate_iana_timezone`. A geographic fact of the *place* (follows `country`), not a configurable property policy — hence it lives here, not on `PropertySettings`. See [FG-008](../../todo/done/fg-008-property-timezone.md).

Replaces lat/lng as `nvarchar(500)` in legacy.

Operator-exposed at `GET/PATCH /properties/{id}/location` (singleton sub-resource, like settings/finance — no `POST`/`DELETE`). The row is **auto-provisioned** with a default `country`/`timezone` derived from `Property.region.country` (via `properties.services.location.ensure_property_location`): on property create, on duplicate, and lazily on first GET, so a property is never location-less. `timezone` is the canonical write here; `/properties/{id}/settings` surfaces it **read-only** for context beside the check-in/out times.

### `PropertyCapacity(AuditedModel)`
Owned by `Property` (CASCADE OneToOne). Hard-deleted with its parent.

- `property` — OneToOne CASCADE primary_key
- `guests` — PositiveSmallInteger
- `additional_guests` — PositiveSmallInteger (default 0)
- `bedrooms`, `ensuites`, `bathrooms` — PositiveSmallInteger
- `size_sqm` — DecimalField(8, 2, null=True, blank=True)

Headline customer-facing counts, kept **independent** of the `Room` list (`PropertyCapacity.bedrooms` is the published total, not derived from individual `Room` rows). Operator-exposed at `GET/PATCH /properties/{id}/capacity` (singleton sub-resource, like settings/finance — no `POST`/`DELETE`); the row is auto-provisioned via `get_or_create` on first GET, so a property is never capacity-less. `GET /properties` also carries a read-only `capacity` block (null when no row — distinct from a zero-`guests` row; `size_sqm` serialised as a string to match this endpoint).

`min_guests` on `/properties` maps to `capacity__guests__gte`, so a property with **no capacity row or `guests = 0` is excluded from quote search**. The exclusion is intentional but no longer silent: the quote builder runs a lenient name search and surfaces a "capacity not set" hint linking to the property, and the capacity editor warns when `guests` is 0. The single source of that rule on the frontend is `isCapacityUnset()` in `features/properties/schemas.ts`.

### `PropertySettings(AuditedModel)`
Owned by `Property` (CASCADE OneToOne). Hard-deleted with its parent. Replaces the legacy `IsDefaultSetting*` boolean salad. Rows are **materialised from the global `PropertyDefaults` singleton at creation** (`properties/services/defaults.py::snapshot_defaults`); after the snapshot each field is a plain, independently-editable value. **`NULL` means genuinely unset** (no longer "inherit") — consumers apply a hardcoded final floor where one exists (`hold_duration_hours`→48, `changeover_day`→`ANY`, `prices_entered_as`→`GROSS`, `min_nights_rental`→1, `availability_default`→`AVAILABLE`, `bookings_require_pre_approval`→`False`; `currency` / `check_in_time` / `check_out_time` stay nullable with no floor).

- `property` — OneToOne CASCADE primary_key
- `availability_default` — TextChoices (`AVAILABLE`, `UNAVAILABLE`, `ON_REQUEST`), null=True
- `bookings_require_pre_approval` — BooleanField(null=True)
- `requires_enquiry_first` — BooleanField(null=True) — when True the property is listed and quotable but the public site hides direct-book affordances; guests are routed through enquiry intake instead. Captures the legacy "Available – Enquire" status (code 20) without giving up the 3-value `Property.status` enum.
- `currency` — FK pricing.Currency PROTECT, null=True
- `check_in_time` — TimeField(null=True, blank=True)
- `check_out_time` — TimeField(null=True, blank=True)
- `changeover_day` — TextChoices (`MON`–`SUN`, `ANY`), null=True. `ANY` means the property accepts check-ins on any weekday (the operator-side "flexible changeover" mode). Search and availability queries must include `ANY` properties on **every** weekday filter — a confirmed legacy bug excluded flexible-changeover villas from specific-weekday searches (see `09-departures.md` "Legacy correctness bugs explicitly fixed").
- `min_nights_rental` — PositiveSmallInteger(null=True)
- `min_nights_rental_note` — TextField(blank=True)
- `prices_entered_as` — TextChoices (`GROSS`, `NET`), null=True
- `hold_duration_hours` — PositiveSmallInteger(null=True) — default lifespan (in hours) of a `BookingHold` created without an explicit `expires_at`. Typical settings: 48 for strict-policy villas (most owners), longer for trusted owners who are relaxed about hold windows. `HoldService` resolves it at hold-creation time, falling back to the hardcoded 48-hour floor when `NULL`. Agents may still override `expires_at` directly on individual `BookingHold` rows for one-off relaxations. See decisions row "Hold duration is per-villa default + per-hold override" in `10-decisions.md`.

Consumers that need a resolved value for a `NULL` column apply the hardcoded floor listed in the section intro at the point of use (e.g. `HoldService` for `hold_duration_hours`, `PricingEngine` for `prices_entered_as`). There is no model-level `effective()` resolver — the field's own value is the value, and `NULL` means genuinely unset.

### `PropertyDefaults(AuditedModel)` — global creation-defaults singleton
Lives in `models/defaults.py`. One row keyed by `pk=1` (`PropertyDefaults.get_solo()` creates it on first access — the same pattern as `core.SystemSettings`). Its field defaults are the seeded starter set; a fresh `get_solo()` and the seed migration agree.

At property creation (`PropertyViewSet.create` and `PropertyLifecycleService.duplicate`, both via `snapshot_defaults`) the singleton's values are copied **field-by-field** into the new property's concrete `PropertySettings` / `PropertyFinance` rows. After the snapshot the rows are independent — **editing a default never re-flows into existing properties**. It carries the settings-side columns above (minus `min_nights_rental_note`'s per-property note nuance) **plus** the finance-*policy* columns (see `03-finance-config.md`); it deliberately excludes per-owner finance data (`contact`, `bank_*`, `tax_number`), since a global default bank account stamped onto every new villa would be wrong.

Operator-exposed at `GET/PATCH /property-defaults` (`IsReservationsWriter`; no `POST`/`DELETE` — the singleton always exists).

## Descriptions

### `PropertyDescription(AuditedModel)`
Normalised rich-text content blocks for the marketing-copy sections of a property. Replaces the legacy flat columns `VillaMaster.WebsiteDescription`, `HouseRules`, `FeatureDescription`, `RoomDescription`, and the unmapped Blazor "Further information" textarea. The API surface (`/properties/{id}/descriptions/{section}`) is a 1:1 mirror of this child table — one row per section per property.

- `property` — FK Property CASCADE
- `section` — TextChoices (`OVERVIEW`, `HOUSE_RULES`, `VILLA_INFO`, `FURTHER_INFO`) — exactly four fixed sections; the API path segments (`overview`, `house-rules`, `villa-info`, `further-info`) are the kebab-cased serialisation of these enum values
- `body` — TextField(blank=True) — markdown / rich text; renderer determined client-side
- `legacy_id` — nullable, indexed

Constraint: `UniqueConstraint(property, section, name="one_description_per_section")` — at most one row per (property, section).

Section mapping for migration:
- `VillaMaster.WebsiteDescription` → `section=OVERVIEW`
- `VillaMaster.HouseRules` → `section=HOUSE_RULES`
- `VillaMaster.FeatureDescription` + `VillaMaster.RoomDescription` → concatenated into `section=VILLA_INFO` (with a paragraph break — the legacy two-column split was a UX artefact, not a semantic distinction; the new UI renders one editor for villa info)
- legacy "Further information" textarea (Blazor-only, unmapped to a column) → `section=FURTHER_INFO` if any content survives the migration audit; otherwise the row is omitted (sections are sparse — a property may have zero, one, or all four)

See reconciliation issue #28.

## Rooms

### `Room(AuditedModel)`
Owned by `Property` (CASCADE FK). Hard-deleted with its parent or directly when an operator removes a room.

- `property` — FK CASCADE
- `name` — CharField (e.g. "Master Suite", "Garden Room")
- `placement` — TextChoices (`MAIN_HOUSE`, `GUEST_HOUSE`, `POOL_HOUSE`,
  `ANNEX` ("Annexe"), `COTTAGE`, `BUNGALOW`, `STUDIO`, `OTHER`), blank=True
  (`""` = unknown — GAP-065 dropped the dishonest `MAIN_HOUSE` default). The
  **building** axis; replaces the legacy `VillaRoomsPlacement` free-text
  lookup, which overloaded building + floor into one string.
- `floor` — TextChoices ladder (`LOWER_GROUND`, `GROUND`, `FIRST`, `SECOND`,
  `THIRD_PLUS`), blank=True (`""` = unknown). Orthogonal to `placement`
  ("first floor of the guest house"). GAP-065; rungs pending owner steer A2.
- `placement_note` — CharField(255, blank=True) — the raw legacy
  `VillaRoomsPlacement.Name` preserved verbatim by `RoomLoader` (no-loss
  guarantee; `data_migration.placement_parsing.parse_placement` fills the two
  axes from it where confident). API-writable so staff can clear it once the
  split is confirmed; read-only helper text in the room form.
- `website_description` — TextField(blank=True)
- `vc_notes` — TextField(blank=True)
- `is_ensuite` — BooleanField(default=False)
- `ensuite_type` — TextChoices (`SHOWER`, `BATH`, `BOTH`), blank=True (`""` =
  unknown; refines `is_ensuite`). DB CheckConstraint
  `room_ensuite_type_implies_is_ensuite`: a typed ensuite must be flagged
  ensuite. The serializer keeps the pair coherent in both directions (a
  non-blank type sets the bool; unticking the bool clears the type). GAP-064.
- `access` — TextChoices (`INSIDE`, `OUTSIDE`), blank=True (`""` = unknown). GAP-064.
- `sort_order` — int

### `RoomBeds(TimestampedModel)`
- `room` — OneToOne CASCADE primary_key
- `double`, `twin_double`, `twin`, `single`, `bunk`, `sofa`, `childrens` — PositiveSmallInteger(default=0)

Keeps the wide bed-count fields out of Room.

### `RoomAttribute(TimestampedModel)` — GAP-064
Admin-curated catalog of per-room amenity tags (aircon, sea view, balcony, …).
Deliberately **separate** from the property `Feature` taxonomy (no category /
`service_type` / pricing coupling). A new amenity is a data row a curator adds
in the Django admin — no migration, serializer, schema or FE change.

- `name` — CharField (curator-editable label)
- `slug` — SlugField(unique) — the stable machine key (code/backfill/tests key on it)
- `description`, `icon`, `sort_order`, `is_active` — the standard catalog shape
- `implies_property_feature` — nullable FK → `Feature`, SET_NULL — the
  data-driven GAP-067 bridge (a room carrying this attribute derives that
  property-level feature; derivation logic itself is GAP-067's). Candidate
  links are attached set-if-NULL by `sync_room_attributes()`
  (`properties/room_attribute_catalog.py`), which migration `0027` calls to
  seed the 9 starter rows and `backfill_room_attrs` re-invokes post-load.

### `RoomAttributeAssignment` — GAP-064
Through model: `room` FK CASCADE (`related_name="attribute_links"`, mirroring
`feature_links`), `attribute` FK **PROTECT** (in-use catalog rows can only be
retired via `is_active`, never deleted), optional `note` CharField(200)
("sea view from the balcony only"), `UniqueConstraint(room, attribute)`.
Presence semantics: present = yes, absent = not claimed (never "confirmed
absent"). Audit-tracked (FG-017) — the API write path is a per-row full-list
diff-writer on `RoomSerializer.attribute_links`; absent field on PATCH leaves
links alone. Read-only catalog endpoint at `/room-attributes` (anon-readable,
serves inactive rows so the room form can keep retired-but-assigned rows
ticked).

## Images

### `PropertyImage(AuditedModel)`
Owned by `Property` (CASCADE). Removed = hard delete (also removes the underlying file via `post_delete` signal). The `is_active` field below toggles visibility on the website without deleting the row. **Single model, single `kind` field.** Replaces six bit-flags (`IsHero`, `IsInterior1`, `IsInterior2`, `IsExterior1`, `IsExterior2`, `IsGallary`).
- `property` — FK CASCADE
- `image` — `ImageField(upload_to="properties/%Y/%m/")` — stored on S3 via `django-storages` (see `00-conventions.md` "Storage backends"). Field declaration uses the standard Django `ImageField`; the storage backend swap is global, not per-field. Uploads land via the two-step `POST /uploads:sign` → client `PUT` to S3 → `POST /properties/{id}/images` flow (see `00-conventions.md` "Two-step signed upload" and reconciliation issue #40); direct streaming through Django is reserved for small files (< 5 MB) via `POST /uploads`.
- `kind` — TextChoices (`HERO`, `INTERIOR`, `EXTERIOR`, `GALLERY`, `FLOOR_PLAN`)
- `name` — CharField(blank=True)
- `description` — TextField(blank=True)
- `sort_order` — int (default 0)
- `is_active` — bool (default True)

Constraints:
- `UniqueConstraint(fields=["property"], condition=Q(kind="HERO", is_active=True), name="unique_active_hero_per_property")` — at most one active hero. A property can exist without a hero (UI uses a fallback); we don't force a OneToOne.

Convenience: `Property.hero_image` as a method returning `images.filter(kind="HERO", is_active=True).first()`.

## Features

### `FeatureCategory(TimestampedModel)`
- `name`, `slug`, `description`, `icon`, `sort_order`, `is_active`

### `Feature(TimestampedModel)`
- `category` — FK FeatureCategory PROTECT
- `name`, `slug`, `description`, `icon`, `sort_order`, `is_active`
- `service_type` — TextChoices (`AMENITY`, `INCLUDED_SERVICE`, `PAID_ADDON`)

Property ↔ Feature uses an explicit `PropertyFeature` through model carrying `sort_order` — the legacy mapping table (`VillaFeaturesMappings`) **did** carry per-link metadata: `MappingOrder`, the operator-chosen per-villa display order. A plain auto-through M2M dropped that order (alphabetical/insertion only), regressing the public-site and editor render against legacy. `PropertyFeature` restores it (`Meta.ordering = ("sort_order", "id")`); the write serializer maps the ordered `feature_ids` list position → `sort_order` and the loader carries `MIN(MappingOrder)` across. See GAP-022.

`service_type` segments the catalogue. The legacy `Tags.razor` admin page (mounted at `/tags`) was a `VillaFeatures` CRUD view filtered by a `ServiceType` enum — there is no separate `Tags` table in the legacy schema. The new design absorbs that admin surface into `/features` with a `?service_type=` filter; there is no `Tag` model, no `PropertyTag` junction, and no `/tags` API resource. See reconciliation issue #8 in `product-design/07-api-schema-reconciliation.md`.

## Services (included, date-ranged) — GAP-037

### `PropertyService(AuditedModel)`
The first-class home for "what's included" in the rate — chef, daily
housekeeping, welcome basket. Promoted out of the legacy free-text
`pricing.RatePlan.inclusion` (owner Loom 2026-06-17) so that inclusions vary
**independently of the rate calendar**: a flat-rate villa with a summer-only
chef is one `RatePlan` + one summer service band, not a duplicate season.

- `property` — FK Property **CASCADE**, `related_name="services"`
- `name` — CharField(128) (e.g. "Private chef")
- `copy` — TextField — **guest-facing** description; seeds the quote "Includes:"
  line (legacy `RatePlan.inclusion`)
- `notes` — TextField(blank=True) — **internal only**, never shown to guests
- `applies_from` — DateField(null=True, blank=True) — **absolute** date (mirrors
  `Extra`); null = open on that end
- `applies_to` — DateField(null=True, blank=True) — null = open; a null/null band
  is **year-round**
- `sort_order` — IntegerField(default=0)
- `is_active` — bool
- `legacy_id` — CharField(64, null, db_index) — loader back-reference

`CheckConstraint propertyservice_applies_from_lte_applies_to`: `applies_from`
null ∨ `applies_to` null ∨ `applies_from ≤ applies_to`. `Meta.ordering =
("property", "sort_order", "id")`; index on `(property, is_active, sort_order)`.

**Informational, never priced.** Cost is already baked into the rate, so unlike
`Extra` a service never flows into a quote total. This keeps three crisp,
non-overlapping inclusion concepts and **does not add a fourth**:
`PropertyService` = included services (date-ranged prose), `pricing.Extra` =
priced add-ons, `Feature(service_type=INCLUDED_SERVICE)` = amenity tags.
`RatePlan.inclusion` is **retired**.

**Engine wiring.** `PricingEngine` derives `breakdown["inclusion"]` from a
property's active services whose absolute band overlaps the stay (reusing
`date_ranges_overlap()`); the projection path maps a future-year stay back onto
the anchor year so projected quotes keep their inclusions. `seed_inclusions`
still copies the joined prose into `reservations.QuotationLine.inclusions` at
line creation (operator-editable thereafter). See `04-pricing.md`.

**API/UX.** List/create nested under `/properties/{id}/services`; retrieve/
update/delete on the flat `/services/{id}` (both `IsReservationsWriter`). The SPA
surfaces them on a dedicated **Services** tab beside Pricing.

## Collections (curated marketing groups)

### `Collection(AuditedModel)`
Lifecycle: `is_active` boolean (already on the model). Hard-deletion is permitted because `CollectionMembership` is CASCADE — removing a collection cleanly removes its memberships, which is desired behaviour. Operators wanting to "hide" a collection without losing memberships toggle `is_active=False` instead.

- `name`, `slug`, `description`, `cover_image`, `sort_order`, `is_active`

### `CollectionMembership(TimestampedModel)`
Explicit through — collections are curated, ordered, and time-bound.
- `collection` — FK CASCADE
- `property` — FK CASCADE
- `sort_order` — int
- `featured_until` — DateField(null=True, blank=True)
- `description` — TextField(blank=True)

Constraint: `UniqueConstraint(collection, property)`.

The through model carries curation metadata that a naive `PUT /properties/{id}/collections` set-replace would silently drop. The API contract is therefore an array of objects, not an array of ids — see reconciliation issue #29 and the API spec at `product-design/04-rest-api-surface.md` §2.2.

## Property–Contact assignment

### `PropertyContactAssignment(AuditedModel)`
Through model linking properties to `accounts.Person`. Lifecycle is the `end_date` field: an open-ended assignment has `end_date IS NULL`; ending the relationship sets `end_date` to the last date the contact held the role. The row is never hidden; queries that want the current set filter `end_date IS NULL`.
- `property` — FK CASCADE
- `contact` — FK accounts.Person PROTECT
- `role` — TextChoices `accounts.ContactRole`
- `start_date` — DateField(null=True, blank=True)
- `end_date` — DateField(null=True, blank=True) — null = open-ended; set to a date when the assignment terminates
- `is_primary` — BooleanField(default=False)

Constraints:
- `UniqueConstraint(property, contact, role, condition=Q(end_date__isnull=True), name="unique_active_role_assignment")` — same role for the same person can't be open twice.
- `UniqueConstraint(property, role, condition=Q(is_primary=True, end_date__isnull=True), name="one_primary_per_role")`.

**Primacy is per-role, never per-villa (GAP-027).** There is no single
property-wide "primary contact": `one_primary_per_role` lets a primary OWNER and
a primary MANAGER coexist. Consumers resolve "the" primary by purpose —
commercial/sales → primary OWNER; operations/concierge → primary MANAGER
(falling back to HOUSEKEEPER); finance → primary OWNER unless an OWNERS_REP is
primary. Do **not** add a property-level `is_primary`; any UI that shows "the
primary contact" must label which role it is resolving. See `10-decisions.md`.

Surfaced on Property:
```python
contacts = M2M("accounts.Person", through="PropertyContactAssignment", related_name="properties")
```

## Things explicitly dropped or moved

- `VillaSite`, `VillaMapping`, `VillaContactGroupMap`, `VillaContactMap`, `VillaContactMapping` — duplicates / dead in legacy
- `IsSync`, `SyncId`, `IsSynced` per-row — moved to `integrations.SyncRecord`
- `ZohoId` on every model — moved to `SyncRecord`
- `OldVillaId` / `OldId` — generalised to `legacy_id` on every domain model
- `VillaStatus` lookup table — collapsed to TextChoices on `Property.status` (`DRAFT` / `ACTIVE` / `ARCHIVED`); legacy 4-row set collapses to 3 values (`live_online` → `ACTIVE`, `pending` → `DRAFT`, `archive` → `ARCHIVED`, `live_offline` → `ARCHIVED` — the "live but not currently bookable" effect is now `PropertySettings.availability_default = UNAVAILABLE`). See reconciliation issue #23.
- `VillaMaster.WebsiteDescription`, `HouseRules`, `FeatureDescription`, `RoomDescription`, plus the unmapped Blazor "Further information" textarea — moved to `PropertyDescription` rows keyed by `section`. The flat-column fields are removed from `Property`. See reconciliation issue #28.
- `AvailabilityStatus` / `ChangeOverDays` / `CalculationType` lookup tables — collapsed to TextChoices
- `VillaRole` lookup table — TextChoices in accounts
