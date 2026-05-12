# 02 — Properties

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
│   ├── settings.py     # PropertySettings, PropertyGroup, GroupSettings
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

### `PropertyGroup(AuditedModel)`
Organisational grouping (e.g. a brand sub-portfolio). Lifecycle: `is_active` boolean. Hard-deletion is blocked by `PROTECT` FK from `Property`.
- `name` — CharField, unique
- `description` — TextField(blank=True)

### `Property(AuditedModel)`
Thin aggregate root. Lifecycle is the explicit `status` enum below — no soft delete. Retiring a property uses `status=ARCHIVED`; reviewing the catalogue uses `?status=` filtering, never a hidden manager.
- `name` — CharField
- `display_name` — CharField
- `slug` — SlugField, unique
- `licence_number` — CharField(blank=True)
- `status` — `TextChoices` (`DRAFT`, `ACTIVE`, `ARCHIVED`) — three values only. `DRAFT` = work-in-progress, hidden from publish targets and search. `ACTIVE` = published, bookable, fanned out to integrations. `ARCHIVED` = retired (decommissioned, end-of-contract, sold). The legacy `live_offline` row collapses into `ARCHIVED`; operators reach the legacy "temporarily not bookable" effect by setting `PropertySettings.availability_default = UNAVAILABLE`, which is a separate axis. See reconciliation issue #23.
- `channel` — `TextChoices` (`DIRECT`, `AGENT`, `WHITE_LABEL`, `INTERNAL`)
- `category` — FK PropertyCategory PROTECT
- `group` — FK PropertyGroup PROTECT
- `region` — FK Region PROTECT
- `features` — M2M to `Feature` (no through; plain)
- `collections` — M2M to `Collection` through `CollectionMembership`
- `nearby_places` — reverse via `PropertyNearbyPlace`
- `legacy_id` — nullable, indexed

Indexes: `slug` (unique), `status`, `(region, status)`, `group`.

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
- `latitude` — DecimalField(9, 6, null=True, blank=True)
- `longitude` — DecimalField(9, 6, null=True, blank=True)

Replaces lat/lng as `nvarchar(500)` in legacy.

### `PropertyCapacity(AuditedModel)`
Owned by `Property` (CASCADE OneToOne). Hard-deleted with its parent.

- `property` — OneToOne CASCADE primary_key
- `guests` — PositiveSmallInteger
- `additional_guests` — PositiveSmallInteger (default 0)
- `bedrooms`, `ensuites`, `bathrooms` — PositiveSmallInteger
- `size_sqm` — DecimalField(8, 2, null=True, blank=True)

### `PropertySettings(AuditedModel)`
Owned by `Property` (CASCADE OneToOne). Hard-deleted with its parent. **Null means inherit from group.** Replaces the legacy `IsDefaultSetting*` boolean salad.

- `property` — OneToOne CASCADE primary_key
- `availability_default` — TextChoices (`AVAILABLE`, `UNAVAILABLE`, `ON_REQUEST`), null=True
- `bookings_require_pre_approval` — BooleanField(null=True)
- `requires_enquiry_first` — BooleanField(null=True) — when True the property is listed and quotable but the public site hides direct-book affordances; guests are routed through enquiry intake instead. Captures the legacy "Available – Enquire" status (code 20) without giving up the 3-value `Property.status` enum. Null = inherit from group.
- `currency` — FK pricing.Currency PROTECT, null=True
- `check_in_time` — TimeField(null=True, blank=True)
- `check_out_time` — TimeField(null=True, blank=True)
- `changeover_day` — TextChoices (`MON`–`SUN`, `ANY`), null=True
- `min_nights_rental` — PositiveSmallInteger(null=True)
- `min_nights_rental_note` — TextField(blank=True)
- `prices_entered_as` — TextChoices (`GROSS`, `NET`), null=True

Resolver lives on the model:

```python
def effective(self, attr: str):
    own = getattr(self, attr)
    if own is not None:
        return own
    return getattr(self.property.group.settings, attr)
```

### `GroupSettings`
Same fields as `PropertySettings` but **non-nullable with defaults** — the group is the inheritance floor and must provide a fallback for every inheritable field.
- `group` — OneToOne PropertyGroup CASCADE primary_key

Created automatically with the `PropertyGroup` (`post_save` signal) and lives for the group's lifetime. Operator-exposed at `GET/PATCH /property-groups/{id}/settings` (no `POST`/`DELETE` — the row is bound to the group). See reconciliation issue #37.

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
- `placement` — TextChoices (`MAIN_HOUSE`, `GUEST_HOUSE`, `POOL_HOUSE`, `ANNEX`, `OTHER`) — replaces `VillaRoomsPlacement` lookup (set is fixed)
- `website_description` — TextField(blank=True)
- `vc_notes` — TextField(blank=True)
- `is_ensuite` — BooleanField(default=False)
- `sort_order` — int

### `RoomBeds(TimestampedModel)`
- `room` — OneToOne CASCADE primary_key
- `double`, `twin_double`, `twin`, `single`, `bunk`, `sofa`, `childrens` — PositiveSmallInteger(default=0)

Keeps the wide bed-count fields out of Room.

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

Property ↔ Feature is plain `ManyToManyField` (auto-through). No per-link metadata in the legacy mapping table beyond audit; plain M2M wins.

`service_type` segments the catalogue. The legacy `Tags.razor` admin page (mounted at `/tags`) was a `VillaFeatures` CRUD view filtered by a `ServiceType` enum — there is no separate `Tags` table in the legacy schema. The new design absorbs that admin surface into `/features` with a `?service_type=` filter; there is no `Tag` model, no `PropertyTag` junction, and no `/tags` API resource. See reconciliation issue #8 in `product-design/07-api-schema-reconciliation.md`.

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
Through model linking properties to `accounts.Contact`. Lifecycle is the `end_date` field: an open-ended assignment has `end_date IS NULL`; ending the relationship sets `end_date` to the last date the contact held the role. The row is never hidden; queries that want the current set filter `end_date IS NULL`.
- `property` — FK CASCADE
- `contact` — FK accounts.Contact PROTECT
- `role` — TextChoices `accounts.ContactRole`
- `start_date` — DateField(null=True, blank=True)
- `end_date` — DateField(null=True, blank=True) — null = open-ended; set to a date when the assignment terminates
- `is_primary` — BooleanField(default=False)

Constraints:
- `UniqueConstraint(property, contact, role, condition=Q(end_date__isnull=True), name="unique_active_role_assignment")` — same role for the same person can't be open twice.
- `UniqueConstraint(property, role, condition=Q(is_primary=True, end_date__isnull=True), name="one_primary_per_role")`.

Surfaced on Property:
```python
contacts = M2M("accounts.Contact", through="PropertyContactAssignment", related_name="properties")
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
