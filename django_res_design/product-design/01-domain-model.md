# 01 — Domain Model

This document maps the entities, relationships, and statuses the Django + DRF backend will model. It is derived from the original .NET / Blazor schema (56 tables, deeply embedded settings) but collapsed and renamed for cleaner Django ORM modelling.

Each section gives: the **entity name**, **key fields** (representative — not exhaustive), **purpose**, and **notable behaviour**. Status enums and cross-cutting conventions follow at the end.

This is **not** the migration file — Django models are generated in the implementation phase. The point of this doc is: agreement on what entities exist, how they relate, and what statuses they carry.

---

## Cross-cutting conventions

Apply to every entity unless noted.

### Soft delete
Every business-relevant entity has `deleted_at` (nullable) and `deleted_by` (FK to `User`, nullable). The default manager filters these out. A separate `all_objects` manager exposes them for admin / audit needs. Truly hard delete only for GDPR erasure (`Guest:anonymize`).

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
- `PropertyDescription` — rich-text section keyed by `section` enum (`overview` / `house_rules` / `villa_info` / `further_info`). One row per section per property.
- `NearbyPOI` — name, type (FK to `POIType`), distance_km, drive_time_min, lat/lng, description. Original `VillaNearBy`.

**Status** (`Property.status`): `draft`, `active`, `archived`. (Simpler than the original `VillaStatus` lookup table.)

**Settings** (split out): originally embedded directly on `VillaMaster`. Now `PropertySettings` 1:1:
- `check_in_time`, `check_out_time`, `min_nights_rental`, `changeover_day` (enum: `mon` ... `sun` or `any`), `requires_pre_approval` (bool), `availability_type`.

**Finance** (split out): `PropertyFinance` 1:1.
- Commission defaults (`commission_type`, `commission_amount`), tax (`tax_rate`, `tax_exempt`), bank account fields, payment-schedule defaults (deposit %, interim %, balance days, SD config). Original `VillaFinance`.

### PropertyCategory
Original `VillaPropertyCategory`. Fields: `name`, `description`. Lookup.

### PropertyGroup
Portfolio / brand group; properties grouped by owner or agency. Fields: `name`, `description`. Original `VillaGroup`.

### Collection
Curated marketing set (e.g., "Luxury Villas", "Pet-Friendly"). Fields: `name`, `slug`, `description`, `is_active`. Original `VillaCollection`.

**Junction**: `PropertyCollection` — (property, collection, order, description, is_active). Original `VillaCollectionsMapping`.

### Feature (amenity)
Field-able amenity (Pool, Sea view, WiFi). Fields: `name`, `description`, `service_type`, `icon` (FK), `default_order`. Original `VillaFeature`.

### FeatureCategory
Grouping for features (Indoor / Outdoor / Connectivity / ...). Fields: `name`, `description`, `icon`, `order`.

**Junction**: `FeatureToCategory` (feature, category). Original `VillaFeaturesCategoryMapping`.

**Property–Feature junction**: `PropertyFeature` — (property, feature, category_override, description_override, order, is_active). Original `VillaFeaturesMapping`.

### Tag
Service-type metadata tag (similar to Feature but separate domain — used for back-office classification). Original `Tags`.

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

Fields: `site_source` (enum — which inbound channel/WP storefront produced the lead), `status` (enum), `source` (enum: `website` / `phone` / `email` / `referral` / `agent`), `assigned_to` (FK to User, nullable), `guest` (FK to Guest), `referral_code`, `agent` (FK to Contact, nullable), `zoho_id`.

Trip-search constraints (denormalised for query speed):
- `from_date`, `to_date`, `dates_flexible` (bool), `flex_days`, `adults`, `children`, `infants`, `min_bedrooms`, `max_bedrooms`, `country` (FK), `regions` (M2M), `features` (M2M), `budget_min_amount`, `budget_max_amount`, `budget_currency`.

Free-form: `notes` (rich text), `preferences_note`.

Tracking: `reference` (e.g., `E-1234`), `user_feedback`, `lost_reason`, `closed_at`.

**Status**: `draft`, `new`, `qualifying`, `quote_sent`, `won`, `lost`.

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

Fields: `property` (FK), `quotation` (FK, nullable), `enquiry` (FK, nullable — denormalised for reporting), `guest` (FK), `payer` (FK to Guest, nullable — defaults to guest), `agent` (FK to Contact, nullable), `reference` (e.g., `BK-2391`), `status` (enum), `site_source` (enum — which inbound channel/WP storefront), `from_date`, `to_date`, `adults`, `children`, `infants`, `currency` (FK), `rental_amount`, `discount_amount`, `discount_reason`, `adjustment_amount`, `adjustment_reason`, `tbc` (to-be-confirmed flag for tentative bookings), `concierge_tier` (`quintessential` / `signature`), `concierge_price_amount`, `concierge_notes`, `internal_notes`, `villa_notes` (passed to property manager), `arrival_time`, `departure_time`, `flight_info`, `special_requests`, `origin` (`enquiry` / `quote` / `direct` / `ota` / `import`), `channel` (enum: `direct_onsite` / `direct_offsite` / `agent_onsite` / `agent_offsite` / `airbnb` / `booking_com` / `vrbo`), `is_owner_confirmed`, `requires_owner_approval` (denorm from property setting at booking time), `zoho_id`.

Aggregate denorm (kept in sync via signals):
- `total_amount`, `paid_amount`, `outstanding_amount` (booking summary right-rail).

**Status** (`Booking.status`):
- `draft`
- `underway` (created, deposit not yet paid)
- `deposit_paid_pending_approval` (deposit paid, awaiting owner approval)
- `deposit_paid` (deposit paid, owner approved or no approval required)
- `confirmed` (balance paid)
- `checked_in`
- `checked_out`
- `completed` (post-departure, all settled)
- `cancelled` (with sub-state for reason category)
- `archived`

### ConciergeLineItem
Original `VillaBookingConcierge` / `VillaConcierge` (the original had two parallel tables — collapsed here).

Fields: `booking` (FK), `service_type` (FK to a concierge taxonomy or free text), `description` (rich text), `currency` (FK), `price_amount`, `supplier` (FK to Contact, nullable), `supplier_cost_amount` (internal-only), `payment_timing` (`now` / `with_balance` / `on_completion` / `included`), `payment_status` (enum), `assigned_to` (FK to User, nullable), `scheduled_at`, `confirmed_at`, `notes`, `display_order`.

**Status** (`ConciergeLineItem.payment_status`): `awaiting`, `sent`, `paid`, `failed`, `included`, `refunded`.

### ArchiveBooking
Soft-delete with separate read surface. Could be a separate table OR a flag on Booking with `archived_at`. Recommendation: a flag with separate manager, exposed as `/bookings/archived` for tidiness. The original had a real archive table; we don't need to perpetuate that.

### BookingNote
Free-text notes attached to a booking. Fields: `booking` (FK), `author` (FK User), `body` (rich text), `is_internal` (bool — internal vs guest-visible).

### BookingDocument
Generated artefacts (confirmation PDF, contract, voucher). Fields: `booking` (FK), `kind` (`confirmation` / `contract` / `voucher` / `invoice` / `receipt`), `file_key` (S3 key), `generated_at`, `generated_by`, `sent_to_guest_at`.

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

**Dropped from original**: `VillaContactMap` (overlapped), `VillaContactRoleMapping` (rolled into the `role` field), `VillaContactGroupMap` (use `ContactPropertyMapping` with property=null indicating group-level? — actually drop; tags handle this).

### Guest
Booking-side customer (separate from `Contact`). Original `VillaClientDetail`.

Fields: `title`, `first_name`, `last_name`, `email`, `phone`, `country` (FK), `region` (FK, nullable), `address_*`, `dietary_notes`, `accessibility_notes`, `language`, `marketing_consent`, `gdpr_anonymized_at` (nullable).

`Guest.bookings` reverse, `Guest.enquiries` reverse, `Guest.quotations` reverse.

### User
Staff account. `email` (PK alt to id), `first_name`, `last_name`, `password_hash`, `is_active`, `is_admin`, `is_2fa_enabled`, `2fa_secret`, `last_login_at`, `last_login_ip`, `failed_attempts`, `locked_until`, `timezone`, `language`, `avatar_key`, `role` (FK or enum). Linked optionally to a `Contact` (for owner-portal users).

`Role` — named permission set. Fields: `name`, `description`, `permissions` (JSON list of permission keys, or M2M).

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

### SecurityDepositTrack (1:1 with Booking)
Fields: `booking` (FK, unique), `kind` (`pre_auth_hold` / `bt_refundable` / `none`), `amount`, `currency`, `due_date`, `hold_expires_at` (for pre-auths), `status`, `release_after_departure_days`, `release_at`, `damage_claim_id` (nullable FK to `DamagesClaim`).

**Status**:
- Pre-auth hold path: `awaiting_details`, `pre_authed`, `released`, `captured`, `expired`, `failed`.
- BT refundable path: `awaiting_bt`, `held`, `refunded`, `partially_refunded`.
- None: `not_applicable`.

### PaymentEvent
A single payment attempt / transaction. Replaces `VillaPaymentDetail` + `VillaCheckoutDetail` (collapsed).

Fields: `track` (polymorphic FK or three nullable FKs to the three tracks above), `gateway` (enum: `stripe` / `manual_bt` / `manual_cash` / `manual_cheque` / `other`), `external_reference` (gateway charge id), `amount`, `currency`, `payer_amount` (what payer actually paid, may differ due to fees), `payer_currency`, `payment_method` (`card` / `bt` / `cheque` / `cash`), `status` (enum), `error_message`, `processed_at`, `idempotency_key`.

**Status**: `pending`, `succeeded`, `failed`, `refunded`, `disputed`, `voided`, `expired`.

### PaymentInstrument
Stored card/bank token for a guest. Fields: `guest` (FK), `gateway`, `gateway_token`, `last_four`, `brand`, `expiry_month`, `expiry_year`, `is_default`, `created_at`. Original `VillaPayment`.

### Refund
Fields: `booking` (FK), `track_kind` (`deposit` / `balance` / `security` / `concierge`), `track_id` (FK to relevant track), `amount`, `currency`, `reason_taxonomy`, `reason_notes`, `requested_by`, `approved_by`, `executed_at`, `gateway_reference`, `method` (`online` / `offline`), `status` (enum). Multiple refunds may stack against one track.

**Status**: `pending`, `approved`, `executing`, `succeeded`, `failed`, `cancelled`, `partially_refunded`.

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
RateCard (1) ──── (many) DiscountRule

Enquiry (1) ──── (0..1) Quotation         (one quote per enquiry typically)
Quotation (1) ──── (many) QuotationLine
QuotationLine (many)── (1) Property
Enquiry (many)──── (1) Guest

Booking (many)──── (1) Property
Booking (many)──── (1) Guest              (lead guest)
Booking (0..1)──── (0..1) Guest           (payer if different)
Booking (many)──── (0..1) Contact         (agent)
Booking (many)──── (0..1) Quotation
Booking (1) ──── (1) DepositPaymentTrack
Booking (1) ──── (1) BalancePaymentTrack
Booking (1) ──── (1) SecurityDepositTrack
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
| `VillaContactGroupMap` | Dropped; tags handle this. |
| `VillaArchiveBooking` | Dropped as separate table; `Booking.is_archived` flag instead. |
| `VillaCodeSentHistory` | Collapsed with `VillaEmailLinkLog` into `CodeAuthLog`. |
| `VillaEmailLinkLog` | Collapsed into `CodeAuthLog`. |
| `VillaCheckoutDetail` | Collapsed into `PaymentEvent`. |
| `VillaPaymentDetail` | Collapsed into `PaymentEvent`. |
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
