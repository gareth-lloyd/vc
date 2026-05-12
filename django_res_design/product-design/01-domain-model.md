# 01 — Domain Model

This document maps the entities, relationships, and statuses the Django + DRF backend will model. It is derived from the original .NET / Blazor schema (56 tables, deeply embedded settings) but collapsed and renamed for cleaner Django ORM modelling.

Each section gives: the **entity name**, **key fields** (representative — not exhaustive), **purpose**, and **notable behaviour**. Status enums and cross-cutting conventions follow at the end.

This is **not** the migration file — Django models are generated in the implementation phase. The point of this doc is: agreement on what entities exist, how they relate, and what statuses they carry.

---

## Cross-cutting conventions

Apply to every entity unless noted.

### Lifecycle (no soft delete)
There is no soft-delete pattern anywhere — no `deleted_at` column, no `all_objects` manager, no `SoftDeleteModel` base class. Every entity's lifecycle is expressed as something a SQL query can see directly:

- **`status` TextChoices** for state-machine models (`Property`, `Booking`, `Quotation`, `Enquiry`, `Refund`, `Payment`, `Contact`, `Guest`, `SecurityDeposit`) — with dated entry timestamps (`archived_at`, `cancelled_at`, `anonymized_at`) when audit demands them.
- **`is_active` boolean** for catalogue/lookup toggles (`Country`, `Region`, `Currency`, `Feature`, `Collection`, `RatePlan`, `RateCard`, `Extra`, `Discount`, etc.).
- **Hard delete** for owned child rows (CASCADE from owner; PROTECT from cross-aggregate references blocks accidents).
- **Append-only event tables** (`BookingEvent`, `PaymentEvent`, `EnquiryEvent`, `WebhookEvent`, `AuditLog`) for history.
- **GDPR erasure** uses anonymization-in-place (`Contact.anonymize()`, `Guest.anonymize()`): PII fields overwritten with sentinels, `status=ANONYMIZED`, row preserved for FK integrity on historical bookings.
- **Merge** flows (`Contact.merge(target)`, `Guest.merge(target)`) rewrite FKs then hard-delete the merged-from row, with an `AuditLog` entry per rewrite.

See `../00-conventions.md` and `../09-departures.md` ("Soft delete eliminated") for full rationale and per-model assignments.

### Audit timestamps
`created_at`, `created_by`, `updated_at`, `updated_by` on every entity. `updated_at` doubles as the etag for concurrency control on PATCH/PUT.

### Not multi-tenant
This is a single-tenant application. There is no `Site` model and no `site` FK on any entity. Investigation of the legacy production database confirmed the `VillaSite` migration was never deployed; the original `vw_villa_sites` view was an *outbound publishing-target registry* (one back-office fans listings out to multiple WordPress storefronts via REST), not a tenant partition.

Where the inbound channel matters for reporting, entities carry a flat `site_source` TextChoices field (currently on `Enquiry` and `Booking`). Outbound fan-out to WordPress storefronts is modelled as `integrations.SyncRecord` with provider `WORDPRESS_SITE` (see `08-integrations.md`). Owner-portal scoping is per-`Contact` via `ContactPropertyMapping` — not tenancy.

### Money fields
Stored as **`Decimal(12, 2) amount + 3-char ISO `currency_code`** — never a bare number. The current original column `Price` becomes `(price_amount, price_currency)`. Reports that aggregate across currencies require an explicit FX policy (snapshot at booking creation? real-time? — open question in `06-verification.md`).

### Status enums
Status fields are stored as short strings (e.g., `"confirmed"`, `"deposit_paid"`), not integers, for legibility in SQL queries and logs. The original used numeric codes (10, 20, ...); we abandon that.

### Timezones
All timestamps stored UTC. `Property.timezone` is the property's IANA timezone (e.g., `Europe/Madrid`); stay-date display uses that. The user's timezone is on `User.timezone` for personal timestamps.

### IDs
Numeric `BigAutoField` PKs for entities frequently referenced in URLs (`Booking.id`, `Property.id`). UUIDs for entities where leaking sequential IDs is undesirable (`MagicLink`, `WebhookEvent`, `AuditLog`).

### Reference numbers
`Booking.reference` (e.g., `BK-12345`) and `Quotation.reference` (e.g., `Q-184`) are user-facing alphanumeric strings. Prefixes (`BK`, `Q`) live in `SystemDefaults`. Separate from the internal PK.

---

## 1. Inventory cluster

### Property
The rentable unit (a villa). Replaces `VillaMaster`.

Key fields: `name`, `display_name`, `slug`, `status` (enum), `category` (FK), `property_group` (FK), `region` (FK), `country` (FK), `currency` (FK), `timezone`, `latitude`, `longitude`, `address_*` fields, `licence_number`, `bedrooms`, `bathrooms`, `ensuites`, `guests`, `additional_guests`, `max_occupancy` (derived), `size_sqm`, `slug`.

Sub-resources (own models):
- `PropertyImage` — image with role tags (`hero`, `interior_1`, `exterior_1`, `gallery`), order, alt text, caption, signed-URL key. Original `VillaPropertyImage`.
- `PropertyRoom` — bedroom with bed config (`bed_double_count`, `bed_single_count`, `bed_bunk_count`, `bed_sofa_count`, `is_ensuite`, `placement`, `order`). Original `VillaRoom` + `VillaRoomsPlacement` (collapsed).
- `PropertyDescription` — rich-text section keyed by `section` enum (`overview` / `house_rules` / `villa_info` / `further_info`). One row per section per property. The backend `Property` carries **no** flat `overview` / `house_rules` / `feature_description` / `room_description` / `notes` text columns — the API `/properties/{id}/descriptions/{section}` (§2.2) is a 1:1 mirror of this child table. See reconciliation issue #28 for the flat-column migration.
- `NearbyPOI` — name, type (FK to `POIType`), distance_km, drive_time_min, lat/lng, description. Original `VillaNearBy`.

**Status** (`Property.status`): `draft`, `active`, `archived`. (Simpler than the original `VillaStatus` lookup table, which had four rows: `live_online`, `live_offline`, `pending`, `archive`. The new design collapses `live_offline` into `archived` — "temporarily not bookable" is expressed via `PropertySettings.availability_default = UNAVAILABLE` instead, which is a separate axis. API actions: `POST /properties/{id}:activate` (any → `active`) and `POST /properties/{id}:archive` (any → `archived`); `POST /properties/{id}:restore` returns an archived property to `draft`. The earlier `:publish` / `:unpublish` verbs are dropped in favour of these state-machine-aligned names. See reconciliation issue #23.)

**Settings** (split out): originally embedded directly on `VillaMaster`. Now `PropertySettings` 1:1:
- `check_in_time`, `check_out_time`, `min_nights_rental`, `changeover_day` (enum: `mon` ... `sun` or `any`), `requires_pre_approval` (bool), `availability_type`.

**Finance** (split out): `PropertyFinance` 1:1, with `GroupFinance` 1:1 on `PropertyGroup` as the inheritance floor.
- Single flat model carrying commission (`commission_calculation_type`, `commission_amount`, `commission_note`), tax (`tax_number`, `tax_is_exempt`, `tax_percentage`), bank account (`bank_account_*` block), payment schedule (`deposit_*` / `interim_*` / `days_*_before_arrival`), and security-deposit policy (`security_deposit_*` block). All nullable on `PropertyFinance`; `null` = inherit from `GroupFinance`. Group-level fields are non-nullable with defaults. Original `VillaFinance`. The earlier 5-OneToOne-children split was collapsed; see reconciliation issue #36.

### PropertyCategory
Original `VillaPropertyCategory`. Fields: `name`, `description`. Lookup.

### PropertyGroup
Portfolio / brand group; properties grouped by owner or agency. Fields: `name`, `description`. Original `VillaGroup`.

### Collection
Curated marketing set (e.g., "Luxury Villas", "Pet-Friendly"). Fields: `name`, `slug`, `description`, `is_active`. Original `VillaCollection`.

**Junction**: `PropertyCollection` — (property, collection, order, description, is_active). Original `VillaCollectionsMapping`.

### Feature (amenity)
Field-able amenity (Pool, Sea view, WiFi). Fields: `name`, `description`, `service_type`, `icon` (FK), `default_order`. Original `VillaFeature`.

`service_type` discriminates the row's domain: `AMENITY` (property feature), `INCLUDED_SERVICE` (contact-service / concierge tier), `PAID_ADDON` (purchasable add-on). The legacy "Tags" admin page (`Tags.razor` at `/tags`) was a *view of `VillaFeatures`* filtered/segmented by this discriminator — there was no separate `Tags` table. See reconciliation issue #8.

### FeatureCategory
Grouping for features (Indoor / Outdoor / Connectivity / ...). Fields: `name`, `description`, `icon`, `order`.

**Junction**: `FeatureToCategory` (feature, category). Original `VillaFeaturesCategoryMapping`.

**Property–Feature junction**: `PropertyFeature` — (property, feature, category_override, description_override, order, is_active). Original `VillaFeaturesMapping`.

### POIType
Type of nearby point (restaurant, beach, airport). Original `VillaNearByLocationType`.

### Region & Country

**Country**: `code` (ISO-2 PK), `name`, `short_name`, `country_order`, `is_active`, `default_tax_rate`. Original `VillaCountry`.

**Region**: `slug` (PK), `name`, `country` (FK). Original `VillaRegion`.

### Currency
`code` (ISO-3 PK), `name`, `symbol`, `symbol_position` (`before` / `after`), `is_default`, `display_order`. Original `VillaCurrency`.

### PriceDisplayConfig
Public website price display per property: POA flag, min/max price, currency symbol placement. Original `VillaWebsitePricing` and `VillaMapping` (collapsed — these overlapped).

### PropertyChannelMapping
External-platform IDs for a property. Fields: `property` (FK), `channel` (enum: `airbnb` / `booking_com` / `vrbo` / `other`), `external_id`, `external_url`, `last_synced_at`, `is_active`.

### PropertyAlternative
"Rent as alternative" or "Rent together" link to a related property. Fields: `property`, `alternative_property`, `relationship_type` (enum: `alternative` / `rent_together`), `order`. Original `VillaRentalAlternative`.

### ChangeOverRule
Per-property bounded set of allowed check-in weekdays. Many rows per property = the set of allowed weekdays for that date window. Zero rows = any day allowed. Backed by `pricing.ChangeOverRule` (lives in the pricing app, FK to `Property`). Fields: `property` (FK), `weekday` (0=Mon ... 6=Sun), `effective_from`, `effective_to` (nullable for open-ended), `notes`. Used by `AvailabilityService.is_available()` and `BookingHold.clean()`. Distinct from `PropertySettings.changeover_day` (single fallback day) and `RateCard.changeover_weekday` (per-card override that supersedes the property rule when set). Operator-facing CRUD at `/properties/{id}/change-over-rules` and the flat alias `/change-over-rules/{id}`; see reconciliation issue #30.

---

## 2. Pricing cluster

Three-level model: **Season → RateCard → RateRule**. Naming choice: keep operator-facing "Season" and "RateCard" terms throughout the UI and API; backend models are `pricing.RatePlan` (= Season), `pricing.RateCard`, and `pricing.RateRule` (see `../04-pricing.md`).

Note: an earlier draft of this doc described `SeasonDateRange` and `OccupancyBand` as first-class entities. They have been removed because production data showed both were vestigial (96% of legacy seasons had one date range; only 3% of rate rows used occupancy banding). Their roles are absorbed into multiple sibling `RateRule` rows on the same card.

### Season
Named pricing period for a property. Original `VillaSeason`. Holds metadata only — no prices.

Fields: `property` (FK), `name`, `notes`, `inclusion` (free amenities text), `currency` (FK), `price_basis` (`gross` / `net`), `effective_from`, `effective_to` (nullable), `is_active`. `carried_rates` and `parent_season` are out of scope unless required by a real workflow — defer.

### RateCard
The operator's editable unit within a season — what they think of as "the summer week price". Attaches min/max nights, changeover restriction, and discount rules. Original `VillaSeasonRate` (the "card-level" parts).

Fields: `season` (FK), `name`, `description`, `min_nights`, `max_nights` (nullable), `changeover_weekday` (nullable; overrides property changeover rule), `sort_order`, `is_active`, `notes`.

The card has **no date range or price of its own** — those live on its child `RateRule` rows.

### RateRule
A price row inside a card: a (date sub-range × party-size band) → nightly/weekly price. Original `VillaSeasonRate` (the "price-row" parts) + `VillaSeasonDate` + `VillaOccupencyPrice`.

Fields: `card` (FK), `date_from`, `date_to`, `min_party`, `max_party`, `priority`, `nightly` (nullable), `weekly` (nullable), `is_poa`, `notes`.

A card with one price = one rule. A card with three occupancy bands = three rules sharing date range with disjoint `(min_party, max_party)`. A card whose price covers two disjoint date sub-ranges = two rules sharing party range with disjoint dates.

### Extra
Property-level catalogue of named charges added at quote time: cleaning fee, pet fee, heating, linen, extra-bed, resort fee, etc. Backed by `pricing.Extra`.

Fields: `property` (FK), `name`, `description`, `kind` (`cleaning` / `pet_fee` / `heating` / `linen` / `extra_bed` / `service_fee` / `resort_fee` / `other`), `calc` (`fixed_per_stay` / `fixed_per_night` / `fixed_per_person` / `fixed_per_person_per_night` / `percent_of_subtotal`), `amount`, `currency` (FK), `is_mandatory`, `applies_from`, `applies_to` (nullable date window — seasonality), `min_party`, `max_party` (nullable — e.g. extra-bed for 5+ guests), `sort_order`, `is_active`, `notes`.

Mandatory extras are applied automatically when their date and party windows match. Optional extras are surfaced in the quote UI for selection and passed through as `opt_in_extras` to the pricing engine.

Tax and commission are **not** Extras — they live on `PropertyFinance` (config) and are applied by the pricing engine via the `PropertyFinance.effective_*` resolvers.

### DiscountRule
First-class entity for length-of-stay / early-bird / last-minute / repeat-guest / promo-code discounts, instead of the original's flag-soup on `VillaSeasonRate`. Backed by `pricing.Discount`. Attaches at the rate-card level (with property-level fallback for property-wide promo codes).

Fields: `card` (FK, nullable), `property` (FK, used when `card` null), `name`, `code` (nullable), `rule_kind` (`length_of_stay` / `early_bird` / `last_minute` / `repeat_guest` / `promo_code`), `kind` (`percent` / `fixed`), `amount`, `min_nights`, `threshold_days` (for early-bird / last-minute), `valid_from`, `valid_to`, `max_uses`, `uses_count`, `is_active`.

---

## 3. Sales pipeline cluster

### Enquiry
Inbound lead, sometimes pre-quotation. Original `VillaEnquire`.

Fields: `site_source` (enum — which inbound channel/WP storefront produced the lead), `status` (enum), `source` (enum: `website` / `phone` / `email` / `referral` / `agent`), `assigned_to` (FK to User, nullable — **internal** staff owner; distinct from `agent`), `guest` (FK to Guest), `referral_code`, `agent` (FK to Contact, nullable — **external** agent / intermediary representing the guest), `zoho_id`. See reconciliation issue #26 for the two-field rationale.

Trip-search constraints (denormalised for query speed):
- `from_date`, `to_date`, `dates_flexible` (bool), `flex_days`, `adults`, `children`, `infants`, `min_bedrooms`, `max_bedrooms`, `country` (FK), `regions` (M2M), `features` (M2M), `budget_min_amount`, `budget_max_amount`, `budget_currency`.

Provenance: `inbound_message` (the original message body the lead submitted via the public form — single immutable field, captured at creation). Operator notes are not stored on the Enquiry row — see `EnquiryNote` below.

Tracking: `reference` (e.g., `E-1234`), `user_feedback`, `lost_reason`, `closed_at`.

**Status**: `draft`, `new`, `qualifying`, `quote_sent`, `won`, `lost`.

### EnquiryNote
Operator-added note attached to an enquiry. Replaces the legacy `VillaEnquire.Notes` and `PreferencesNote` flat columns, which the original Blazor UI rendered as overwrite-only textareas with no authorship or audit trail.

Fields: `enquiry` (FK), `author` (FK User), `kind` (`general` / `internal` / `preferences`), `body` (rich text), `is_pinned`, `created_at`, `updated_at`. Mutation audit lives in `AuditLog`; the row itself is hard-deleted on remove.

### Quotation
Header for a multi-villa quote. Original `VillaQuotationMaster`.

Fields: `enquiry` (FK, nullable), `guest` (FK), `agent` (FK to Contact, nullable), `reference` (e.g., `Q-184`), `status` (enum), `from_date`, `to_date`, `total_weeks`, `guests` (adult+child), `created_by`, `sent_at`, `zoho_id`.

**Status**: `draft`, `sent`, `viewed`, `converted`, `withdrawn`, `lost`.

### QuotationLine
One villa option within a quotation. Original `VillaQuotationDetail`.

Fields: `quotation` (FK), `property` (FK), `from_date`, `to_date`, `nights`, `price_amount`, `price_currency`, `is_manual` (operator-overrode auto price), `manual_price_reason`, `display_order`, `guest_notes` (shown to guest), `internal_notes`, `state` (enum: `offered` / `selected` / `declined`).

---

## 4. Bookings cluster

### Booking
The confirmed reservation. Original `VillaBooking`.

Fields: `property` (FK), `quotation` (FK, nullable), `enquiry` (FK, nullable — denormalised for reporting), `guest` (FK), `payer` (FK to Guest, nullable — defaults to guest), `agent` (FK to Contact, nullable — **external** agent / intermediary), `assigned_to` (FK to User, nullable — **internal** staff owner; distinct from `agent`. Backs `?assigned_to=` filter and `:assign` action — see reconciliation issue #26), `reference` (e.g., `BK-2391`), `status` (enum), `site_source` (enum — which inbound channel/WP storefront), `from_date`, `to_date`, `adults`, `children`, `infants`, `currency` (FK), `rental_amount`, `discount_amount`, `discount_reason`, `adjustment_amount`, `adjustment_reason`, `tbc` (to-be-confirmed flag for tentative bookings), `concierge_tier` (`quintessential` / `signature`), `concierge_price_amount`, `arrival_time`, `departure_time`, `flight_info`, `special_requests`, `origin` (`enquiry` / `quote` / `direct` / `ota` / `import`), `channel` (enum: `direct_onsite` / `direct_offsite` / `agent_onsite` / `agent_offsite` / `airbnb` / `booking_com` / `vrbo`), `is_owner_confirmed`, `requires_owner_approval` (denorm from property setting at booking time), `zoho_id`.

Note: operator notes (legacy `Notes`, `ConciergeNotes`, internal-notes, villa-notes textareas) are not stored as flat columns. They live in `BookingNote` (below), keyed by `kind`.

Aggregate denorm (kept in sync via signals):
- `total_amount`, `paid_amount`, `outstanding_amount` (booking summary right-rail).

**Status** (`Booking.status`) — single source of truth lives in `06-availability.md`:
- `draft`
- `pending_owner_approval` (when property requires it)
- `awaiting_deposit`
- `deposit_paid`
- `awaiting_balance`
- `balance_paid`
- `checked_in`
- `checked_out` (terminal — post-stay; reached via manual `check_out()` or beat-task auto-completion)
- `cancelled` (with sub-state for reason category) — terminal
- `expired` (deposit deadline missed) — terminal
- `declined` (owner rejected pending approval) — terminal

Note: `archived` is **not** a status value. It is a boolean flag (`Booking.is_archived` + `archived_at`) that tidies terminal-state bookings out of the operator's default list. Archive is orthogonal to status — a `cancelled` booking and a `checked_out` booking are both candidates for archival; both stay queryable. See `06-availability.md` for the full state machine and the `:archive`/`:restore`/`:modify-dates`/`:modify-guests`/`:resend-confirmation` semantics.

### ConciergeLineItem
Original `VillaBookingConcierge` / `VillaConcierge` (the original had two parallel tables — collapsed here). There is no upstream `ConciergeService` catalogue model: legacy `VillaConciergeServices` held only 2 tier-label rows ("Quintessential", "Signature"); those collapse to a `ConciergeTier` TextChoices on the line item and the per-item name/description/unit-price/unit/currency live directly on the row. See reconciliation issue #34.

Fields: `booking` (FK), `tier` (`quintessential` / `signature`), `name`, `description` (rich text), `quantity`, `unit` (`day` / `stay` / `event` / `hour`), `unit_price`, `currency` (FK), `supplier` (FK to Contact, nullable), `supplier_cost_amount` (internal-only), `payment_timing` (`now` / `with_balance` / `on_completion` / `included`), `payment_status` (enum), `assigned_to` (FK to User, nullable), `scheduled_at`, `confirmed_at`, `notes`, `display_order`.

**Status** (`ConciergeLineItem.payment_status`): `awaiting`, `sent`, `paid`, `failed`, `included`, `refunded`.

### ArchiveBooking
Resolved (issue #7): a flag on `Booking` (`is_archived` + `archived_at`), not a separate table. A dedicated queryset filter exposes the archived set at `/bookings/archived`. Operator-facing actions live on the main resource as `POST /bookings/{id}:archive` / `:restore` and are only permitted from terminal states (`checked_out`, `cancelled`, `expired`, `declined`). There is no `DELETE /bookings/{id}` — once a booking exists it is preserved for audit; mistakes are corrected via `:cancel` with an explanatory reason. The legacy `VillaArchiveBooking` table is dropped.

### BookingNote
Operator-added note attached to a booking. Canonical store for what the legacy schema spread across `VillaBooking.Notes`, `VillaBooking.ConciergeNotes`, and the unmapped Blazor "Internal booking information" / "Villa notes" textareas.

Fields: `booking` (FK), `author` (FK User), `kind` (`general` / `internal` / `concierge` / `villa`), `body` (rich text), `is_pinned`, `visibility` (`staff_only` / `owner` / `guest`), `created_at`, `updated_at`. Mutation audit lives in `AuditLog`; the row itself is hard-deleted on remove.

The three-textarea legacy edit page is preserved as a UX by binding each textarea to a `kind`-filtered subset of the collection.

### BookingDocument
Generated artefacts (confirmation PDF, contract, voucher). Fields: `booking` (FK), `kind` (`confirmation` / `contract` / `voucher` / `invoice` / `receipt`), `file_key` (S3 key), `generated_at`, `generated_by`, `sent_to_guest_at`.

### TermsVersion
Append-only versioning of the legal copy (T&Cs) shown at quotation acceptance and booking confirmation. Backed by `reservations.TermsVersion`. Fields: `version` (e.g. `2026-01`, unique slug), `body_markdown`, `published_at`, `is_current` (bool — unique constraint with condition `is_current=True` so exactly one row is current at any time).

`Quotation.terms_version` and `Booking.terms_version` snapshot the version active at creation; older rows stay queryable for audit and dispute resolution. There is no `PATCH` or `DELETE` — correcting a published version means publishing a new one. Operator-facing surface is `GET/POST /terms-versions` + `POST /terms-versions/{version}:publish`; see §2.29 of `04-rest-api-surface.md` and reconciliation issue #33.

---

## 5. Availability cluster

### AvailabilityRecord
A single per-date status entry per property. Original `VillaAvailability`.

Fields: `property` (FK), `date` (or `from_date` + `to_date` if we model ranges — recommendation: store as one row per date for query simplicity; range writes expand server-side), `status` (enum), `morning_status` (nullable enum for half-day), `afternoon_status` (nullable enum for half-day), `booking` (FK, nullable — linked when status is booked-style), `hold_expires_at` (nullable — for holds), `reason` (enum for unavailable subtypes: `owner_stay` / `maintenance` / `closure`), `notes`, `created_by`.

**Status** values:
- `available`
- `available_enquire` (operator must confirm before quoting)
- `on_hold` (auto-expires)
- `booked_provisional` (deposit unpaid)
- `booked_pending_approval` (owner approval pending)
- `booked` (confirmed)
- `unavailable` (with `reason` subtype)

Hold-expiry is processed by a Celery beat job — no client endpoint.

---

## 6. People cluster

### Contact
Owner, manager, agent, accountant, supplier — anyone other than the booking-side guest. Original `VillaContact`.

Fields: `title`, `first_name`, `last_name`, `company`, `address_*`, `country` (FK), `preferred_method` (`email` / `phone` / `whatsapp`), `notes`, `is_active`, `zoho_id`. (No `password` etc. — Contacts are not auth users; if they need portal access, a `User` row is linked with a `contact` FK.)

Sub-resources:
- `ContactEmail` — `contact` FK, `email`, `is_primary`, `is_verified`.
- `ContactPhone` — `contact` FK, `phone`, `is_primary`.

### ContactPropertyMapping
The granular permission/notification mapping. Original `VillaContactMapping`.

Fields: `contact` (FK), `property` (FK), `role` (enum: `owner` / `manager` / `agent` / `concierge` / `accountant` / `read_only` / `viewer` / `custom`), `is_primary_contact`, `is_cc`, `notes`.

Permission flags (only consulted when `role=custom`; otherwise role implies):
- `access_info`, `access_avail`, `access_rates`, `access_booking`, `access_confirm_auth`, `access_slip`.
- `notify_info`, `notify_avail`, `notify_rates`, `notify_booking`, `notify_confirm_req`, `notify_slip`.

When a role preset is chosen, the booleans are still set (computed from the role) but the UI hides them behind a `Customize` toggle. If the user customises, `role` switches to `custom` and the displayed label becomes "Owner (custom)" or similar.

**Dropped from original**: `VillaContactMap` (overlapped), `VillaContactRoleMapping` (rolled into the `role` field), `VillaContactGroupMap` (dropped — group-level contact assignment was unused in legacy; if a real need surfaces, add a `PropertyGroup` FK on `ContactPropertyMapping` or a sibling table).

### Guest
Booking-side customer (separate from `Contact`). Original `VillaClientDetail`.

Fields: `title`, `first_name`, `last_name`, `email`, `phone`, `country` (FK), `region` (FK, nullable), `address_*`, `dietary_notes`, `accessibility_notes`, `language`, `marketing_consent`, `gdpr_anonymized_at` (nullable).

`Guest.bookings` reverse, `Guest.enquiries` reverse, `Guest.quotations` reverse.

### User
Staff account. `email` (PK alt to id), `first_name`, `last_name`, `password_hash`, `is_active`, `is_superuser` (Django built-in — replaces legacy `IsSystemAdmin`), `is_2fa_enabled`, `2fa_secret`, `last_login_at`, `last_login_ip`, `failed_attempts`, `locked_until`, `timezone`, `language`, `avatar_key`, `role` (fixed `StaffRole` TextChoices: `ADMIN` / `RESERVATIONS` / `ACCOUNTS` / `VIEWER`). Linked optionally to a `Contact` (for owner-portal users).

`User.role` is a hard-coded enum, not a row in a table. Each enum value maps to a fixed Django `auth.Group` (created via migration) that carries the actual `auth.Permission` rows. Admin UI exposes the enum as a read-only `/roles` list and `?role=` filter; there is no `/roles` CRUD. The legacy app had no editable staff-role table either — staff power was a single `UserMaster.IsSystemAdmin` boolean. See reconciliation issue #9.

**Do not confuse `User.role` (staff capability) with `PropertyContactAssignment.role` (how a `Contact` relates to a `Property`: owner / manager / agent / housekeeper / owner's-rep — the `accounts.ContactRole` enum, §6 below).** They are different concepts; only `User.role` is what `/roles` API refers to.

`UserSession` — active sessions for self-management.

### MagicLink
For owner-portal passwordless login. Fields: `email`, `token_hash`, `expires_at`, `used_at`, `created_for_contact` (FK).

---

## 7. Money flows cluster

Three explicit payment-track entities, one shared payment-instrument concept, one refund concept, one payment-event audit trail.

### DepositPaymentTrack (1:1 with Booking)
Fields: `booking` (FK, unique), `amount`, `currency`, `due_date`, `percentage_of_rental` (or null if overridden), `is_overridden`, `status` (enum), `waived_at`, `waive_reason`.

**Status**: `awaiting`, `link_sent`, `viewed`, `paid`, `partially_paid`, `failed`, `waived`, `refunding`, `refunded`.

### BalancePaymentTrack (1:1 with Booking)
Fields: `booking` (FK, unique), `amount`, `currency`, `due_date`, `is_overdue` (denorm bool), `status`, `reminders_sent_count`, `last_reminder_at`, `next_reminder_at`, `waived_at`.

**Status**: same as deposit, plus `overdue`-tagged via separate flag (state and overdue are independent in this design — improvement #18).

### SecurityDeposit (1:1 with Booking, when applicable)
First-class workflow object. Mirrors the `Refund` pattern: this is the workflow row; gateway-transaction audit lives on spawned `Payment(purpose=SECURITY_DEPOSIT)` rows linked via `meta['security_deposit_id']`. Earlier drafts of this doc called this `SecurityDepositTrack` — renamed for symmetry with `Refund` and to reflect that the row is a workflow object, not a passive "track".

Fields: `booking` (FK, unique when not deleted), `kind` (`pre_auth_hold` / `bt_refundable`), `amount`, `currency`, `due_at`, `hold_expires_at` (for pre-auths), `status`, `release_after_departure_days`, `release_scheduled_for`, `released_at`, `captured_amount` (nullable, set on partial/full claim), `refunded_amount` (nullable, set on BT refunds), `damage_claim` (nullable FK to `DamageClaim`), `requested_by` / `requested_at`. When a property has no security deposit policy, no row is created — no `not_applicable` state. (Idempotency for the `:create` action lives in the generic `core.IdempotencyRecord` table, not on this model — see reconciliation issue #39.)

**Status**:
- Pre-auth hold path: `awaiting_details`, `pre_authed`, `released`, `captured`, `expired`, `failed`. Transitions: `:hold` (AWAITING_DETAILS → PRE_AUTHED), `:release` (PRE_AUTHED → RELEASED, manual or Celery beat), `:claim` (PRE_AUTHED → CAPTURED, requires `damage_claim` link), gateway timeout (PRE_AUTHED → EXPIRED).
- BT refundable path: `awaiting_bt`, `held`, `refunded`, `partially_refunded`. Transitions: `:mark-paid` (AWAITING_BT → HELD, records a manual `Payment(provider=MANUAL_BANK_TRANSFER, status=SUCCEEDED)`), `:release` (HELD → REFUNDED, opens and executes a `Refund(purpose_track=SECURITY_DEPOSIT)`), `:claim` (HELD → PARTIALLY_REFUNDED, opens a refund for `amount - captured_amount`).

API: `/bookings/{id}/security` and `/bookings/{id}/security/payments/{id}:hold|:release|:claim` (§2.12); `:mark-paid` advances the SD row (not a `Payment.mark_paid` call), creating the manual-BT `Payment` row underneath. See reconciliation issue #25. BT refunds reuse the `Refund` workflow so separation-of-duties applies uniformly.

### PaymentEvent
A single payment attempt / transaction. Replaces `VillaPaymentDetail` + `VillaCheckoutDetail` (collapsed).

Fields: `track` (polymorphic FK or three nullable FKs to the three tracks above), `gateway` (enum: `stripe` / `manual_bt` / `manual_cash` / `manual_cheque` / `other`), `external_reference` (gateway charge id), `amount`, `currency`, `payer_amount` (what payer actually paid, may differ due to fees), `payer_currency`, `payment_method` (`card` / `bt` / `cheque` / `cash`), `status` (enum), `error_message`, `processed_at`, `idempotency_key`.

**Status**: `pending`, `succeeded`, `failed`, `refunded`, `disputed`, `voided`, `expired`, `waived`. `waived` is operator-applied to a scheduled `DEPOSIT` or `BALANCE` row (the `:waive` API action) — terminal, no money moves; the booking advances as if the payment had succeeded. `:mark-paid` is a separate transition that writes a manual receipt (`provider=MANUAL_BANK_TRANSFER`, `status=succeeded`); not a status of its own. See reconciliation issue #24.

### PaymentInstrument
Per-charge audit record of the card/bank instrument used. Fields: `guest` (FK), `gateway`, `gateway_token`, `last_four`, `brand`, `expiry_month`, `expiry_year`, `created_at`. Original `VillaPayment`. **Note:** v1 does not expose a multi-method wallet to operators or guests — `PaymentMethod` API endpoints are deferred (see reconciliation issue #13). Records are write-once metadata attached to a `PaymentEvent`, not a reusable selection list; the `is_default` flag and tokenize/detach surfaces revisit when multi-method picker is in scope.

### Refund
First-class workflow object for money flowing back to the guest. Owns the approve/reject/execute lifecycle; spawns one `PaymentEvent` (purpose=refund) per gateway transaction on execute.

Fields: `booking` (FK), `against_payment` (FK PaymentEvent, nullable — the original inbound charge being refunded, when known), `purpose_track` (`deposit` / `balance` / `security` / `adjustment` / `goodwill`), `amount`, `currency`, `reason_code` (`cancellation` / `overpayment` / `goodwill` / `security_deposit_release` / `duplicate_charge` / `other`), `reason_notes`, `method` (`online_gateway` / `manual_bank_transfer` / `offline`), `requested_by`, `requested_at`, `approved_by`, `approved_at`, `rejected_by`, `rejected_at`, `rejection_reason`, `executed_by`, `executed_at`, `cancelled_at`, `settled_at`, `failure_reason`, `gateway_reference`, `status` (enum). Multiple refunds may stack against one track or one inbound payment (partial refunds are modelled as multiple `Refund` rows, not as a status). (Idempotency for `:create` / `:execute` lives in the generic `core.IdempotencyRecord` table — see reconciliation issue #39.)

**Status**: `pending`, `approved`, `rejected`, `executing`, `succeeded`, `failed`, `cancelled`.

**State machine** (terminal states: `rejected`, `cancelled`, `succeeded`, `failed`):
`pending` → `approved` (`:approve`) | `rejected` (`:reject`) | `cancelled` (`:cancel`)
`approved` → `executing` (`:execute`) | `cancelled` (`:cancel`)
`executing` → `succeeded` (gateway webhook success) | `failed` (gateway webhook failure / Celery exhaustion)

**Separation of duties**: `approved_by` must differ from `requested_by` (override permission `payments.refund.self_approve` for small-value refunds; enforced in the service layer). `executed_by` may equal `approved_by` by default; orgs that need a third actor enforce that in policy.

### DamagesClaim
For security-deposit captures. Fields: `booking` (FK), `description`, `amount`, `itemized_lines` (JSON list or related table), `photos` (M2M to uploaded file keys), `created_by`, `accepted_by_guest_at`.

### CancellationPolicy
Named template (Strict / Moderate / Flexible) + per-villa override. Fields: `name`, `slug`, `description`, `tiers` (JSON list — days-before-arrival thresholds + refund percents).

`Booking.cancellation_policy` is a snapshot (FK + denormalised tier rules captured at booking time) so policy changes don't retroactively affect existing bookings.

---

## 8. Communications cluster

### EmailTemplate
Versioned. Fields: `key` (e.g., `deposit_request`, `booking_confirmation`, `owner_approval_request`), `subject_template`, `body_template` (rich text or markdown), `is_active`, `version`. The original maintained these in `wwwroot/templates/email/` as HTML files; we move them into the DB for runtime editing.

### EmailLog
Every sent email. Fields: `template` (FK), `to_email`, `cc_emails`, `bcc_emails`, `subject_rendered`, `body_rendered`, `booking` (FK, nullable), `enquiry` (FK, nullable), `quotation` (FK, nullable), `gateway_message_id`, `status` (enum: `queued` / `sent` / `delivered` / `opened` / `bounced` / `failed`), `sent_at`, `delivered_at`, `opened_at`, `bounce_reason`.

### CodeAuthLog
Magic-link / 2FA code dispatches. Original `VillaCodeSentHistory` / `VillaEmailLinkLog` (collapsed).

Fields: `kind` (`magic_link` / `2fa_code` / `password_reset`), `recipient_email`, `token_hash`, `expires_at`, `used_at`, `ip_requested_from`.

---

## 9. Integrations cluster

### ZohoSyncJob
Fields: `kind` (`contacts` / `properties` / `enquiries` / `quotations` / `bookings`), `status`, `started_at`, `finished_at`, `records_processed`, `records_failed`, `error_summary`, `triggered_by`.

### ChannelSyncJob
Outbound sync to OTAs. Fields: `channel` (`airbnb` / `booking_com` / `vrbo`), `property` (FK, nullable for portfolio-wide), `kind` (`availability` / `rates` / `content`), `status`, similar metadata.

### WebhookEvent
Inbound webhook audit log. Fields: `provider` (`stripe` / `airbnb` / `booking_com` / `vrbo` / `zoho` / `other`), `event_type`, `external_id`, `payload` (JSON), `signature_valid` (bool), `processed_at`, `processing_status` (`pending` / `processed` / `failed` / `replayed`), `error_message`.

---

## 10. Reports & exports cluster

### ReportRun
Audit of report executions. Fields: `kind` (`occupancy` / `revenue` / `owner_statement` / `commissions` / `tax` / `refunds` / `enquiry_funnel`), `parameters` (JSON), `requested_by`, `started_at`, `completed_at`, `row_count`, `export_format`, `file_key`, `status`, `scheduled_report` (FK, nullable).

### ScheduledReport
Recurring report. Fields: `kind`, `parameters` (JSON), `cron_expression`, `recipients` (list of emails), `format`, `is_active`, `last_run_at`, `next_run_at`, `created_by`.

### Export (async job)
Generic file export. Fields: `kind`, `parameters` (JSON), `requested_by`, `format`, `status`, `file_key`, `expires_at`. Generic `/jobs/{id}` polling surface.

---

## 11. Cross-cutting cluster

### AuditLog
The single source of truth for who-changed-what. Fields: `id` (UUID), `actor` (FK User, nullable for system actors), `actor_kind` (`user` / `system` / `webhook` / `scheduled_job`), `action` (verb string, e.g., `booking.confirm` / `availability.set_block`), `entity_kind`, `entity_id`, `before` (JSON), `after` (JSON), `correlation_id` (UUID — groups related changes within one operation), `request_id` (HTTP request correlation), `at` (timestamp), `metadata` (JSON for extra context). Indexed on `(entity_kind, entity_id, at)` and `(actor, at)`.

### Notification (in-app)
Fields: `recipient` (FK User), `kind`, `title`, `body`, `link`, `is_read`, `created_at`, `read_at`.

### NotificationPreference
Per-user, per-kind, per-channel. Fields: `user` (FK), `kind`, `channel` (`email` / `in_app` / `slack`), `is_enabled`.

### FeatureFlag
Fields: `key`, `description`, `is_enabled_default`, `enabled_for_users` (M2M), `rollout_percent`. Read-through with caching.

### SystemDefaults
Global key/value config. Replaces `VillaConfigPropertyDefault` (which was actually system-level defaults misnamed). Fields: `key`, `value` (JSON), `description`. Admin only.

---

## Relationship summary (cardinalities that matter)

```
Property (1) ──── (many) PropertyImage
Property (1) ──── (many) PropertyRoom
Property (1) ──── (many) PropertyDescription
Property (1) ──── (many) NearbyPOI
Property (1) ──── (many) Season
Property (1) ──── (many) AvailabilityRecord
Property (1) ──── (many) Booking
Property (1) ──── (many) Extra
Property (1) ──── (1)   PropertySettings
Property (1) ──── (1)   PropertyFinance
Property (1) ──── (1)   PriceDisplayConfig
Property (many)──(many) Feature           (via PropertyFeature)
Property (many)──(many) Collection        (via PropertyCollection)
Property (many)──(many) Contact           (via ContactPropertyMapping)
Property (many)──── (1) Region
Property (many)──── (1) Country
Property (many)──── (1) Currency
Property (many)──── (1) PropertyGroup
Property (many)──── (1) PropertyCategory

Region (many)──── (1) Country

Season (1) ──── (many) RateCard
RateCard (1) ──── (many) RateRule
RateCard (1) ──── (many) DiscountRule       (card-scoped discounts)
Property (1) ──── (many) DiscountRule       (property-wide promo codes; card null)
Property (1) ──── (many) ChangeOverRule

Enquiry (1) ──── (0..1) Quotation         (one quote per enquiry typically)
Enquiry (1) ──── (many) EnquiryNote
Enquiry (1) ──── (many) EnquiryEvent      (state-machine + assignment timeline)
Enquiry (many)──── (0..1) User            (assigned_to — internal staff owner)
Quotation (1) ──── (many) QuotationLine
QuotationLine (many)── (1) Property
Enquiry (many)──── (1) Guest

Booking (many)──── (1) Property
Booking (many)──── (1) Guest              (lead guest)
Booking (0..1)──── (0..1) Guest           (payer if different)
Booking (many)──── (0..1) Contact         (agent — external)
Booking (many)──── (0..1) User            (assigned_to — internal staff owner)
Booking (many)──── (0..1) Quotation
Booking (1) ──── (1) DepositPaymentTrack
Booking (1) ──── (1) BalancePaymentTrack
Booking (0..1)── (0..1) SecurityDeposit   (when property requires one)
Booking (1) ──── (many) ConciergeLineItem
Booking (1) ──── (many) BookingNote
Booking (1) ──── (many) BookingDocument
Booking (1) ──── (many) Refund

Each PaymentTrack (1) ──── (many) PaymentEvent
Each PaymentTrack (1) ──── (many) Refund

Contact (1) ──── (many) ContactEmail
Contact (1) ──── (many) ContactPhone
Contact (many)──(many) Property           (via ContactPropertyMapping)
Contact (0..1)──── (0..1) User            (when contact has portal access)

Guest (1) ──── (many) Booking
Guest (1) ──── (many) Enquiry
Guest (1) ──── (many) Quotation
Guest (1) ──── (many) PaymentInstrument

User (1) ──── (many) UserSession
User (1) ──── (many) Notification

AuditLog records any (actor, entity) pair.
```

---

## What's dropped or collapsed from the original

For the migration script's reference.

| Original table | Disposition |
|---|---|
| `VillaSite` | Dropped. Was never used as a tenant partition in production (migration never deployed); legacy `vw_villa_sites` was an outbound WordPress publishing-target registry, modelled now via `integrations.SyncRecord` with `provider=WORDPRESS_SITE`. The inbound-channel signal lives on `Enquiry.site_source` / `Booking.site_source` enums. |
| `VillaMaster` | Split into `Property` + `PropertySettings` + `PropertyFinance` + `PriceDisplayConfig`. |
| `VillaConfigPropertyDefault` | Renamed `SystemDefaults` (it was system-level despite the name). |
| `VillaWebsitePricing` | Collapsed with `VillaMapping` into `PriceDisplayConfig`. |
| `VillaMapping` | Collapsed into `PriceDisplayConfig`. |
| `VillaContactMap` | Dropped; overlapped with `VillaContactMapping`. |
| `VillaContactRoleMapping` | Dropped; role rolled into `ContactPropertyMapping.role`. |
| `VillaContactGroupMap` | Dropped; group-level contact assignment was unused in legacy. |
| `VillaArchiveBooking` | Dropped as separate table; `Booking.is_archived` flag instead. |
| `VillaCodeSentHistory` | Collapsed with `VillaEmailLinkLog` into `CodeAuthLog`. |
| `VillaEmailLinkLog` | Collapsed into `CodeAuthLog`. |
| `VillaCheckoutDetail` | Replaced by `payments.Payment` rows (one per `purpose ∈ {DEPOSIT, BALANCE, SECURITY_DEPOSIT}` per booking). Legacy `/checkouts` endpoint dropped; query via `/payments?purpose=…`. |
| `VillaPaymentDetail` | Collapsed into `payments.Payment` (+ `payments.PaymentEvent` for the audit stream). |
| `VillaPayment` | Renamed `PaymentInstrument`. |
| `VillaPaymentStatus` | Dropped as separate lookup table; enum on `PaymentEvent.status`. |
| `VillaBookingConcierge` + `VillaConcierge` | Collapsed into `ConciergeLineItem`. |
| `VillaBookingDetail` | Folded into `Booking` (one-row-per-booking was always 1:1). |
| `VillaStatus` | Dropped as lookup table; enum on `Property.status`. |
| `AvailabilityStatus` | Dropped as lookup table; enum on `AvailabilityRecord.status`. |
| `EnquireStatus` | Dropped as lookup table; enum on `Enquiry.status`. |
| `DepositType`, `CalculationType`, `ChangeOverDay` | Dropped as lookup tables; enums on relevant fields. |
| `VillaQuotationMaster` + `VillaQuotationDetail` | Renamed `Quotation` + `QuotationLine`. |
| `VillaEnquire` | Renamed `Enquiry`. |
| `VillaBooking` | Renamed `Booking`. |
| `VillaClientDetail` | Renamed `Guest`. |
| `VillaClientPrefMaster`, `ClientPreferenceDetail` | Folded into `Guest.preferences` (rich text) or dropped if unused. Verify with ops during migration. |

All other `Villa*` tables map 1:1 to entities above with the `Villa` prefix removed.
