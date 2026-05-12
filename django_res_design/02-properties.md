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

### `PropertyGroup(SoftDeleteModel)`
Organisational grouping (e.g. a brand sub-portfolio).
- `name` — CharField, unique
- `description` — TextField(blank=True)

### `Property(SoftDeleteModel)`
Thin aggregate root.
- `name` — CharField
- `display_name` — CharField
- `slug` — SlugField, unique
- `overview` — TextField(blank=True)
- `house_rules` — TextField(blank=True)
- `feature_description`, `room_description` — TextField(blank=True)
- `notes` — TextField(blank=True)
- `licence_number` — CharField(blank=True)
- `status` — `TextChoices` (`DRAFT`, `ACTIVE`, `OFFLINE`, `ARCHIVED`)
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

### `PropertyLocation(SoftDeleteModel)`
- `property` — OneToOneField(Property, on_delete=CASCADE, primary_key=True)
- `address_line_1`, `address_line_2`, `address_line_3` — CharField(blank=True)
- `post_code` — CharField(blank=True)
- `locality_town` — CharField(blank=True)
- `locality_region` — CharField(blank=True)
- `country` — FK Country PROTECT
- `latitude` — DecimalField(9, 6, null=True, blank=True)
- `longitude` — DecimalField(9, 6, null=True, blank=True)

Replaces lat/lng as `nvarchar(500)` in legacy.

### `PropertyCapacity(SoftDeleteModel)`
- `property` — OneToOne CASCADE primary_key
- `guests` — PositiveSmallInteger
- `additional_guests` — PositiveSmallInteger (default 0)
- `bedrooms`, `ensuites`, `bathrooms` — PositiveSmallInteger
- `size_sqm` — DecimalField(8, 2, null=True, blank=True)

### `PropertySettings(SoftDeleteModel)`
**Null means inherit from group.** Replaces the legacy `IsDefaultSetting*` boolean salad.

- `property` — OneToOne CASCADE primary_key
- `availability_default` — TextChoices (`AVAILABLE`, `UNAVAILABLE`, `ON_REQUEST`), null=True
- `bookings_require_pre_approval` — BooleanField(null=True)
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
Same fields as `PropertySettings` but **non-nullable with defaults** — the group must provide a fallback for every inheritable field.
- `group` — OneToOne PropertyGroup CASCADE primary_key

## Rooms

### `Room(SoftDeleteModel)`
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

### `PropertyImage(SoftDeleteModel)`
**Single model, single `kind` field.** Replaces six bit-flags (`IsHero`, `IsInterior1`, `IsInterior2`, `IsExterior1`, `IsExterior2`, `IsGallary`).
- `property` — FK CASCADE
- `image` — `ImageField(upload_to="properties/%Y/%m/")`
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

## Collections (curated marketing groups)

### `Collection(SoftDeleteModel)`
- `name`, `slug`, `description`, `cover_image`, `sort_order`, `is_active`

### `CollectionMembership(TimestampedModel)`
Explicit through — collections are curated, ordered, and time-bound.
- `collection` — FK CASCADE
- `property` — FK CASCADE
- `sort_order` — int
- `featured_until` — DateField(null=True, blank=True)
- `description` — TextField(blank=True)

Constraint: `UniqueConstraint(collection, property)`.

## Property–Contact assignment

### `PropertyContactAssignment(SoftDeleteModel)`
Through model linking properties to `accounts.Contact`.
- `property` — FK CASCADE
- `contact` — FK accounts.Contact PROTECT
- `role` — TextChoices `accounts.ContactRole`
- `start_date` — DateField(null=True, blank=True)
- `end_date` — DateField(null=True, blank=True)
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
- `VillaStatus` lookup table — collapsed to TextChoices on `Property.status`
- `AvailabilityStatus` / `ChangeOverDays` / `CalculationType` lookup tables — collapsed to TextChoices
- `VillaRole` lookup table — TextChoices in accounts
