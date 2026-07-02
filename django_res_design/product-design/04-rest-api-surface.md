# 04 — REST API Surface (Specification)

This document is a **table-of-contents level inventory** of endpoints the Django + DRF backend must expose. Payload schemas, status code enumeration, and DRF code are explicitly out of scope — they belong to the implementation phase. This file lists *what endpoints exist*, not *what they accept and return*.

---

## 1. API Conventions

### Base path & versioning
- All endpoints mounted under `/api/v1/`.
- Version is path-based (`/api/v1/`, `/api/v2/`). Minor additive changes are unversioned; breaking changes bump the major.
- Public-facing read endpoints (consumed by the marketing site or partner SPAs) are nested under `/api/v1/public/` with a separate auth/anon contract.
- Webhook receivers live under `/api/v1/webhooks/` and use signature-based auth, not the session/JWT auth.
- Signed-URL endpoints (when any land — none in v1; iCal feeds deferred to v1.1 per reconciliation issue #12) live under `/api/v1/feeds/`.

### Resource naming
- Plural, lowercase, hyphenated (`/properties`, `/rate-cards`, `/email-templates`).
- Detail resource is `/{resource}/{id}` where `id` is the numeric PK or a slug, depending on resource (slug for `properties`, `regions`, `countries`, `sites`, `collections`; numeric otherwise).
- Sub-resources nest where the child has no meaningful identity outside the parent (`/properties/{id}/rooms`, `/bookings/{id}/concierge-items`).
- Cross-cutting child resources that the frontend treats as first-class (images, contacts, payments) are exposed both nested for write and flat for global list/search.

### Auth
- `Authorization: Bearer <token>` header on all authenticated endpoints. Token issued by `/auth/login` (short-lived access + refresh).
- Public endpoints accept anonymous; gated endpoints return 401 without a token, 403 with an insufficiently scoped token.
- Owner-portal token scope (`owner`) is a distinct auth scope from staff scopes (`staff`, `admin`).
- Site context derived from token claims; `X-Site` header may override for staff impersonating site context.

### Pagination
- Cursor pagination by default for endpoints expected to grow unbounded (`bookings`, `enquiries`, `email-logs`, `audit-log`, `payments`). (`GET /availability` is deliberately unpaginated: it returns raw band arrays bounded by the ≤50-property cap and the date window.)
- Page-number pagination for small bounded lists (`regions`, `countries`, `features`, `currencies`, `roles`).
- Standard query params: `?cursor=`, `?limit=` (cursor); `?page=`, `?page_size=` (page). `limit` capped server-side.
- All list responses include `next` / `previous` and a `count` for page-number style.

### Filtering, search, sort
- Filtering uses query-string fields matching resource attributes (`?status=draft`, `?site=ibiza&region=balearics`).
- Multi-value filters via repeated key or comma-list (`?status=draft,confirmed`).
- Date range filters use `<field>_after` / `<field>_before` (e.g., `?check_in_after=2026-06-01`).
- Free-text search uses `?q=`.
- Sorting uses `?ordering=field,-other_field` (DRF convention).

### Includes / sparse fields
- Optional relation inclusion via `?include=images,rooms,features` to inline related collections. Default response is shallow (FK ids only).
- Sparse fieldsets via `?fields=id,name,slug` for list endpoints.

### List vs detail
- List endpoint returns lighter representation (no rich text, no nested collections).
- Detail endpoint returns full representation including small-cardinality nested collections (images, rooms, features) inline.

### Bulk operations
- Bulk create/update via `POST /{resource}/bulk` or `PATCH /{resource}/bulk` with an array body.
- Bulk delete via `POST /{resource}/bulk-delete`.
- Long-running bulk ops return a job handle and live under `/jobs/{id}` for polling.

### Action (verb) endpoints
- Non-CRUD state transitions use the colon-verb convention: `POST /bookings/{id}:confirm`, `POST /quotations/{id}:send`, `POST /enquiries/{id}:convert`.
- Action endpoints never accept a representation of the resource — only the action's parameters.
- Action endpoints return the updated resource (or a job handle if async).

### Webhooks
- Inbound: `POST /webhooks/{provider}` (flywire, zoho). HMAC signature header verified on raw body bytes. (OTA inbound — airbnb/booking.com/vrbo — is future scope; see reconciliation issue #11.)
- Outbound webhooks (we emit) are not part of MVP — no `/webhook-subscriptions` resource. Internal integrations (Zoho push, WordPress fan-out) run via Celery jobs configured through `/system/integrations`. See reconciliation issue #17.

### File upload
- Two-step: `POST /uploads:sign` returns a signed S3 (or equivalent) URL the client PUTs to. Then the client `POST`s the resulting key to the consuming resource (e.g., `POST /properties/{id}/images`).
- For small files (avatar, doc < 5 MB) direct multipart `POST` is also accepted at `POST /uploads`.

### Sub-resource convention
- Sub-resource list: `GET /properties/{id}/rates`.
- Sub-resource create: `POST /properties/{id}/rates`.
- Sub-resource detail: `GET /properties/{id}/rates/{rate_id}` OR `GET /rates/{rate_id}` (flat alias). Flat alias supported where the sub-resource has a globally unique id.

### Error format
- Standard problem-detail JSON shape with `code`, `detail`, `field_errors`. Implementation decides exact field names.

### Idempotency
- ~~`Idempotency-Key` header honored on all `POST` action endpoints and payment-creating endpoints.~~ **Superseded (2026-07-02, FG-005)** — the header/middleware surface was never built and the backing `core.IdempotencyRecord` table is dropped; idempotency is a request-body `idempotency_key` handled by the service layer (see `django_res/CLAUDE.md` §"State-mutating services accept `idempotency_key`").

---

## 2. Endpoint Inventory

### 2.1 Auth & Profile

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/auth/login` | Credential login, returns access + refresh tokens | anon |
| POST | `/auth/logout` | Invalidate refresh token | user |
| POST | `/auth/refresh` | Exchange refresh for new access token | anon (refresh) |
| POST | `/auth/password-reset:request` | Email reset link | anon |
| POST | `/auth/password-reset:confirm` | Submit new password with reset token | anon |
| POST | `/auth/2fa:challenge` | Begin 2FA challenge after primary auth | partial-auth |
| POST | `/auth/2fa:verify` | Submit OTP / TOTP code | partial-auth |
| POST | `/auth/2fa:enroll` | Begin TOTP enrollment | user |
| POST | `/auth/2fa:disable` | Disable 2FA for self | user |
| GET | `/auth/me` | Current user profile, site context, scopes | user |
| PATCH | `/auth/me` | Update own profile | user |
| POST | `/auth/me/password` | Change password (requires current) | user |
| GET | `/auth/permissions` | Discovery: what scopes/resources the caller can access | user |
| GET | `/auth/sessions` | List active sessions for self | user |
| DELETE | `/auth/sessions/{id}` | Revoke a session | user |
| POST | `/auth/magic-link:request` | Owner-portal passwordless link | anon |
| POST | `/auth/magic-link:consume` | Exchange magic-link token for session | anon |

---

### 2.2 Properties (Villas)

Core CRUD plus heavy sub-resource surface. Property is the most-edited entity in the admin UI.

#### Core
| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/properties` | List | filters: `status`, `category`, `group`, `region`, `country`, `site`, `collection`, `min_bedrooms`, `max_bedrooms`, `min_guests`, `q`; `include=`; `ordering=` |
| POST | `/properties` | Create | staff |
| GET | `/properties/{id}` | Detail | accepts numeric id or slug |
| PATCH | `/properties/{id}` | Partial update | |
| DELETE | `/properties/{id}` | Soft-delete ("should not have existed"). **Distinct from `:archive`** — `:archive` is a lifecycle state for retired properties (still queryable); `DELETE` is for data-quality cleanup. See reconciliation issue #23. | |
| POST | `/properties/{id}:restore` | Return an archived property to `status = draft`. Allowed only from `archived`. (Distinct from `DELETE /properties/{id}`'s soft-delete reversal, which isn't exposed as an action — once a property is hard-deleted via the cleanup tooling, it stays gone.) |
| POST | `/properties/{id}:duplicate` | Clone villa with sub-resources | |
| POST | `/properties/{id}:activate` | Set `status = active`. Allowed from `draft` or `archived`. |
| POST | `/properties/{id}:archive` | Set `status = archived`. Allowed from `draft` or `active`. State-machine verb on `Property.status`. (Distinct from `Booking:archive`, which is a flag mutation — different concepts, intentionally same verb name because both move the row "out of the active set".) |

#### Images
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/images` | List images, role-tagged |
| POST | `/properties/{id}/images` | Attach uploaded image (key from `/uploads:sign`) |
| PATCH | `/properties/{id}/images/{image_id}` | Update role tag, caption, alt |
| DELETE | `/properties/{id}/images/{image_id}` | Remove |
| POST | `/properties/{id}/images:reorder` | Reorder by id list |
| POST | `/properties/{id}/images:set-hero` | Designate hero |

#### Rooms
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/rooms` | List rooms with bed config |
| POST | `/properties/{id}/rooms` | Add room |
| PATCH | `/properties/{id}/rooms/{room_id}` | Update |
| DELETE | `/properties/{id}/rooms/{room_id}` | Remove |
| POST | `/properties/{id}/rooms:reorder` | Reorder |

#### Features / Amenities
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/features` | Attached features |
| PUT | `/properties/{id}/features` | Replace full set (idempotent multi-attach) |
| POST | `/properties/{id}/features` | Add one |
| DELETE | `/properties/{id}/features/{feature_id}` | Remove |

#### Descriptions (rich text blocks)

Backed by `properties.PropertyDescription` (per-property × per-section child rows; see `02-properties.md`). Sections are a fixed enum: `overview`, `house-rules`, `villa-info`, `further-info`. Sections are sparse — a property may have zero, one, or all four rows. `PUT` upserts (creates or replaces); `DELETE` removes the row (server returns empty body for the section). The flat columns the legacy `VillaMaster` carried (`WebsiteDescription`, `HouseRules`, `FeatureDescription`, `RoomDescription`) are migrated into rows of this child table — see reconciliation issue #28.

| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/descriptions` | All present description sections, each `{section, body, updated_at}` |
| GET | `/properties/{id}/descriptions/{section}` | Fetch one; 404 if not present |
| PUT | `/properties/{id}/descriptions/{section}` | Upsert one section (`{body}` only — section comes from the path) |
| DELETE | `/properties/{id}/descriptions/{section}` | Remove the row for this section |

#### Nearby points-of-interest
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/nearby` | List POIs |
| POST | `/properties/{id}/nearby` | Add POI |
| PATCH | `/properties/{id}/nearby/{poi_id}` | Update |
| DELETE | `/properties/{id}/nearby/{poi_id}` | Remove |

`NearbyPlaceType` (the FK target) is a small curated taxonomy exposed read-only at `GET /nearby-place-types` for dropdown population (see §2.3). No write CRUD in v1; seeded via data migration. See reconciliation issue #35.

#### Change-over rules (allowed check-in weekdays)
Per-property bounded set of weekdays on which a booking may start. Many rows per property = the set of allowed weekdays for that date window. Zero rows = any day allowed. Used by `AvailabilityService.is_available()` and `BookingHold.clean()`. Distinct from `PropertySettings.changeover_day` (single fallback day). Changeover is property-level only — no per-card override (GAP-007 retired `RateCard.changeover_weekday`). See reconciliation issue #30.

| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/change-over-rules` | List rules; filters: `?effective_on=` (YYYY-MM-DD; returns rules active on that date) |
| POST | `/properties/{id}/change-over-rules` | Add rule (body: `{weekday, effective_from, effective_to?, notes?}`) |
| GET | `/change-over-rules/{id}` | Detail (flat alias) |
| PATCH | `/change-over-rules/{id}` | Update |
| DELETE | `/change-over-rules/{id}` | Remove |

#### Contact mapping (which contacts are linked to this villa)
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/contacts` | List contact-property mappings (with role, permission flags) |
| POST | `/properties/{id}/contacts` | Attach contact with role + flags |
| PATCH | `/properties/{id}/contacts/{mapping_id}` | Update flags |
| DELETE | `/properties/{id}/contacts/{mapping_id}` | Detach |

#### Finance / settings on the villa
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/settings` | Currency, check-in/out, min nights, changeover day, pre-approval. Null fields inherit from `/property-groups/{id}/settings`. Also surfaces `timezone` **read-only** (sourced from the location). |
| PATCH | `/properties/{id}/settings` | Update settings. `timezone` is read-only here — write it via `/location`. |
| GET | `/properties/{id}/location` | Postal address, country, lat/lng, and `timezone`. Singleton sub-resource (no `POST`/`DELETE`); auto-provisioned with country/timezone derived from `region.country` on create/duplicate and lazily on first GET, so a property is never location-less. |
| PATCH | `/properties/{id}/location` | Update location. Sole writer of `timezone` (a geographic fact of the place — see [FG-008](../todo/done/fg-008-property-timezone.md)). |
| GET | `/properties/{id}/capacity` | Headline guest/room counts (`guests`, `additional_guests`, `bedrooms`, `ensuites`, `bathrooms`, `size_sqm`). Singleton sub-resource (no `POST`/`DELETE`); auto-provisioned via `get_or_create` on first GET. |
| PATCH | `/properties/{id}/capacity` | Update capacity. `guests = 0` (or no row) excludes the property from `?min_guests=` quote search — the quote builder surfaces a "capacity not set" hint rather than silently dropping it. |
| GET | `/properties/{id}/finance` | Flat finance config: commission, tax, bank account, payment schedule, security-deposit policy. Null fields inherit from `/property-groups/{id}/finance`. See reconciliation issue #36 (5-OneToOne-children split collapsed to one flat model). |
| PATCH | `/properties/{id}/finance` | Update |

#### Collections

`CollectionMembership` (the through model — see `02-properties.md`) carries `sort_order`, `featured_until`, and a per-membership `description`. A naive `PUT` with a bare id-list would silently discard those fields on every replace, so the body shape is an array of **membership objects**, not ids. The PUT is a full-set replace: memberships present in the request body are upserted (created or updated) keyed by `collection` slug/id; memberships absent from the request body are removed. Use `POST` / `DELETE` on the singular nested path below for non-destructive single-membership edits. See reconciliation issue #29.

| Method | Path | Purpose | Body |
|---|---|---|---|
| GET | `/properties/{id}/collections` | List memberships for this property, each `{collection, sort_order, featured_until, description}` | — |
| PUT | `/properties/{id}/collections` | Full-set replace of memberships | `[{collection: <slug-or-id>, sort_order: int, featured_until: date \| null, description: str}, ...]` |
| POST | `/properties/{id}/collections` | Attach to one collection (idempotent on `collection`) | `{collection, sort_order, featured_until, description}` |
| PATCH | `/properties/{id}/collections/{collection}` | Update one membership's through-fields | `{sort_order?, featured_until?, description?}` |
| DELETE | `/properties/{id}/collections/{collection}` | Detach from one collection | — |

#### Importers
| Method | Path | Purpose |
|---|---|---|
| POST | `/properties/{id}:import-from-zoho` | Pull from Zoho CRM |

> Channel-manager mappings (Airbnb / Booking.com / VRBO external IDs and outbound sync) are out of MVP scope; see reconciliation issue #11. The domain model retains `PropertyChannelMapping` as a forward-looking entity but no endpoints are exposed in v1.

---

### 2.3 Property Metadata

Catalogue resources — mostly thin CRUD, all admin-scoped writes, anon-readable for public endpoints under `/public/`.

#### Categories
| Method | Path |
|---|---|
| GET / POST | `/property-categories` |
| GET / PATCH / DELETE | `/property-categories/{id}` |

#### Groups (portfolio/brand)
| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/property-groups` | List / create |
| GET / PATCH / DELETE | `/property-groups/{id}` | Detail |
| GET / PATCH | `/property-groups/{id}/settings` | Group-level settings — the inheritance floor for `PropertySettings` null fields. Same fields as `/properties/{id}/settings`. Row is auto-created with the group; no `POST`/`DELETE`. See reconciliation issue #37. |
| GET / PATCH | `/property-groups/{id}/finance` | Group-level finance config — the inheritance floor for `PropertyFinance` null fields. Single flat resource (commission / tax / bank account / payment schedule / security deposit policy), same shape as `/properties/{id}/finance`. Row is auto-created with the group; no `POST`/`DELETE`. See reconciliation issues #36 and #38. |

#### Collections (marketing sets)
| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/collections` | |
| GET / PATCH / DELETE | `/collections/{slug}` | |
| GET | `/collections/{slug}/properties` | Properties in this collection, each `{property, sort_order, featured_until, description}` |
| PUT | `/collections/{slug}/properties` | Full-set replace of memberships. Body: `[{property: <id-or-slug>, sort_order, featured_until, description}, ...]` — same through-field semantics as `/properties/{id}/collections` (see §2.2 and reconciliation issue #29). |

#### Features (amenities)
| Method | Path |
|---|---|
| GET / POST | `/features` |
| GET / PATCH / DELETE | `/features/{id}` |
| GET / POST | `/feature-categories` |
| GET / PATCH / DELETE | `/feature-categories/{id}` |

#### Regions
| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/regions` | List filter: `?has_properties=true` narrows to regions holding ≥1 property (opt-in; `false`/absent = full list). Feeds the staff geo dropdowns (quote builder, property/timeline filters). |
| GET / PATCH / DELETE | `/regions/{slug}` | |
| GET | `/regions/{slug}/properties` | |

#### Countries
| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/countries` | List filter: `?has_properties=true` — same semantics as `/regions` (via `regions__properties`). |
| GET / PATCH / DELETE | `/countries/{code}` | |

#### Currencies
| Method | Path |
|---|---|
| GET / POST | `/currencies` |
| GET / PATCH / DELETE | `/currencies/{code}` |
| GET | `/currencies/{code}/rates` | FX rates (if cached server-side) |

#### Nearby place types
Small curated taxonomy (airport, beach, restaurant, station, etc.) FK'd from `PropertyNearbyPlace`. Read-only in v1 — seeded via data migration; no write CRUD. The FE uses this to populate the type dropdown when adding a POI to a property. See reconciliation issue #35.

| Method | Path | Purpose |
|---|---|---|
| GET | `/nearby-place-types` | List active place types (returns `[{id, name, icon}]`) |

#### Sites (multi-tenant brands)
| Method | Path |
|---|---|
| GET / POST | `/sites` |
| GET / PATCH / DELETE | `/sites/{slug}` |
| GET | `/sites/{slug}/settings` |
| PATCH | `/sites/{slug}/settings` |

---

### 2.4 Pricing

Three-level hierarchy: **Season → Rate Card → Rate Rule**. Seasons are scoped to a property; rate cards live inside a season; rate rules carry the actual prices (one row per date sub-range × party-size band). Occupancy bands are not a separate resource — they are sibling rate rules sharing a date range with different party ranges. Date ranges are not a separate resource — they are columns on rate rule.

Backed by `pricing.RatePlan` (= Season), `pricing.RateCard`, and `pricing.RateRule` respectively.

#### Seasons
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/seasons` | List seasons for villa |
| POST | `/properties/{id}/seasons` | Create season |
| GET | `/seasons/{id}` | Detail (flat alias) — includes nested rate cards (with their rules inlined) |
| PATCH | `/seasons/{id}` | Update |
| DELETE | `/seasons/{id}` | Delete |
| POST | `/seasons/{id}:duplicate` | Clone with rate cards + rules |

#### Rate cards
| Method | Path | Purpose |
|---|---|---|
| GET | `/seasons/{id}/rate-cards` | List rate cards in season |
| POST | `/seasons/{id}/rate-cards` | Create (rules are read-only nested — add them via `/rate-cards/{id}/rules`) |
| GET | `/rate-cards/{id}` | Detail (flat alias) — rules inlined by default |
| PATCH | `/rate-cards/{id}` | Update card metadata (rules are managed via the rule endpoints, not a nested array) |
| DELETE | `/rate-cards/{id}` | Delete |
| POST | `/rate-cards/{id}:duplicate` | Clone within or across seasons |

#### Rate rules (price rows)
Granular CRUD for individual rules. Use these when adding a single occupancy band or splitting a date sub-range without rewriting the whole card.
| Method | Path | Purpose |
|---|---|---|
| GET | `/rate-cards/{id}/rules` | List rules in card |
| POST | `/rate-cards/{id}/rules` | Add rule |
| GET | `/rules/{id}` | Detail (flat alias) |
| PATCH | `/rules/{id}` | Update |
| DELETE | `/rules/{id}` | Delete |

Rule writes are validated serializer-side against the `RateRule` DB
constraints (date order, party band, price-or-POA, POA-excludes-price, and
the same-priority overlap EXCLUDE — date and party ranges are inclusive), so
violations return `400 field_errors` instead of a 500.

#### Extras (cleaning fee, pet fee, heating, linen, extra-bed, etc.)
Property-scoped catalogue of named charges added at quote time. Backed by `pricing.Extra` (see `04-pricing.md`). Each extra has a kind (`CLEANING`, `PET_FEE`, `HEATING`, `LINEN`, `EXTRA_BED`, `SERVICE_FEE`, `RESORT_FEE`, `OTHER`), a calc method, an amount, optional date and party-size windows, and an `is_mandatory` flag.

Tax and commission are **not** Extras — they live under property finance config (`/properties/{id}/finance`) and are applied automatically by the pricing engine.

| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/extras` | List extras for villa; filters: `kind`, `is_mandatory`, `is_active` |
| POST | `/properties/{id}/extras` | Create |
| GET | `/extras/{id}` | Detail (flat alias) |
| PATCH | `/extras/{id}` | Update |
| DELETE | `/extras/{id}` | Archive |
| POST | `/extras/{id}:duplicate` | Clone (optionally onto another property via body `target_property_id`) |

#### Discounts (promo codes, length-of-stay, early-bird, last-minute, repeat-guest)
Backed by `pricing.Discount` (see `04-pricing.md`). A discount attaches either to a single `RateCard` (`card` FK set) or to a whole property (`card` null, `property` set — used for property-wide promo codes that aren't tied to one rate card). The `code` field is unique across the system for `PROMO_CODE` rule kinds. See reconciliation issue #32.

| Method | Path | Purpose |
|---|---|---|
| GET | `/discounts` | List; filters: `property`, `card`, `rule_kind`, `code`, `is_active`, `valid_on=YYYY-MM-DD` |
| POST | `/discounts` | Create (body must set either `card` or `property` — server enforces `card IS NOT NULL OR property IS NOT NULL`) |
| GET | `/discounts/{id}` | Detail |
| PATCH | `/discounts/{id}` | Update |
| DELETE | `/discounts/{id}` | Delete (hard — historical bookings keep their pricing via `pricing_snapshot`) |
| GET | `/rate-cards/{id}/discounts` | Nested list scoped to one rate card |
| POST | `/rate-cards/{id}/discounts` | Create within a rate card (sets `card` from path) |
| GET | `/properties/{id}/discounts` | Nested list of this property's discounts (both card-scoped and property-wide) |
| POST | `/properties/{id}/discounts` | Create a property-wide discount (sets `property` from path, leaves `card` null) |
| POST | `/discounts:lookup-code` | Validate a promo code without exposing the catalogue. Body: `{property_id, code, date_from, date_to, party}`. Response: `{discount_id, name, kind, amount, applies: true}` or 404. Used by the public quote / quotation-acceptance UI; rate-limited |

#### Website price display
| Method | Path | Purpose |
|---|---|---|
| GET | `/properties/{id}/price-display` | POA / min-max / symbol placement |
| PATCH | `/properties/{id}/price-display` | Update |

#### Pricing computation helper
| Method | Path | Purpose | Notes |
|---|---|---|---|
| POST | `/pricing:quote` | Compute total for property + dates + guests + opt-in extras | Body accepts `opt_in_extras: [<extra_id>, ...]`; mandatory extras are applied automatically. Stateless calc, used by quotation UI |
| POST | `/pricing:quote-bulk` | Compute prices for many `(property × dates × party)` tuples in one call — no quotation is created | Stateless. Body: `{requests: [{property_id, date_from, date_to, adults, children, opt_in_extras?}, ...], currency?}`. Response: `{quotes: [{property_id, available: bool, total, breakdown, ...}, ...]}`. Used by FE comparison tables / search-result cards that want to show prices alongside a list of properties without creating any persistent quotation state. **Distinct from** `/availability:search` (no price) and `/quotations:search-villas` (creates/updates a Quotation draft). See reconciliation issue #44. |

---

### 2.5 Availability

Calendar reads are the highest-RPS endpoint group; expect heavy caching.

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/properties/{id}/availability` | Calendar slice | `?from=&to=` required |
| POST | `/properties/{id}/availability` | Write block(s) — manual block, hold, owner-stay | accepts single or range |
| PATCH | `/availability/{id}` | Update one record | |
| DELETE | `/availability/{id}` | Clear block | |
| GET | `/availability` | Multi-villa timeline bands (shipped) | `?property_ids=&from=&to=` all required; ≤50 ids (mirrors the property page size) else 400; staff-only. Returns `{records, bookings}`: `records` = live operator holds (expiry-checked, booking-linked holds excluded), `bookings` = occupying bookings incl. resting legacy DRAFT rows, with `guest_name`/`reference`/`status`. Range bands, not per-day cells — the frontend derives display status. |
| POST | `/availability:search` | Find villas matching date + guest criteria — **availability only, no prices** | Body: `{date_from, date_to, adults, children, filters: {region?, country?, min_bedrooms?, features?, ...}}`. Response is a property list with available/blocked status per villa for the given window. **Distinct from** `/pricing:quote-bulk` (which computes prices) and `/quotations:search-villas` (which creates/updates a Quotation draft). See reconciliation issue #44. |
| POST | `/availability:bulk-block` | Block range across many villas | admin |
| POST | `/availability/{id}:extend-hold` | Extend a hold's expiration | |
| POST | `/availability/{id}:release-hold` | Release a hold | |

Hold-expiration runs server-side on a schedule — no client endpoint.

---

### 2.6 Enquiries

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/enquiries` | List | filters: `status`, `site`, `assigned_to`, `source`, `created_after`, `created_before`, `q` |
| POST | `/enquiries` | Create (typically from public marketing site) | accepts anon via `/public/` mirror |
| GET | `/enquiries/{id}` | Detail | |
| PATCH | `/enquiries/{id}` | Update | |
| DELETE | `/enquiries/{id}` | Archive | |
| POST | `/enquiries/{id}:assign` | Assign owner / agent | |
| POST | `/enquiries/{id}:convert` | Convert to quotation | returns new quotation id |
| POST | `/enquiries/{id}:close` | Mark closed-lost / closed-won | |
| POST | `/enquiries/{id}:reopen` | Reopen | |
| GET | `/enquiries/{id}/activity` | Activity timeline (messages, status changes) | |
| POST | `/enquiries/{id}/notes` | Add internal note | |
| GET | `/enquiries/{id}/notes` | List notes | |
| POST | `/public/enquiries` | Public enquiry submission | anon, captcha-protected |

---

### 2.7 Quotations

Headers + line items; quote-send is a notable side-effecting action.

| Method | Path | Purpose |
|---|---|---|
| GET | `/quotations` | List, filter by `status`, `enquiry`, `guest`, `created_after` |
| POST | `/quotations` | Create header, with optional nested `lines` — header + lines + pricing + holds succeed or fail as one transaction (the builder's atomic save; a hold conflict 409s and rolls everything back). `lines` is create-only |
| GET | `/quotations/{id}` | Detail incl. lines |
| PATCH | `/quotations/{id}` | Update |
| DELETE | `/quotations/{id}` | Archive |
| POST | `/quotations/{id}:send` | Email quote to guest |
| POST | `/quotations/{id}:duplicate` | Clone |
| POST | `/quotations/{id}:convert` | Convert chosen line(s) to booking(s) |
| POST | `/quotations/{id}:withdraw` | Mark withdrawn |

#### Quotation lines (per-villa lines)
| Method | Path | Purpose |
|---|---|---|
| GET | `/quotations/{id}/lines` | List lines |
| POST | `/quotations/{id}/lines` | Add line to an existing quotation (the builder creates its initial lines nested on `POST /quotations`) |
| PATCH | `/quotations/{id}/lines/{line_id}` | Update |
| DELETE | `/quotations/{id}/lines/{line_id}` | Remove |
| POST | `/quotations/{id}/lines:reorder` | Reorder |

#### Helper
| Method | Path | Purpose |
|---|---|---|
| POST | `/quotations:search-villas` | Operator-facing villa shortlist for a `Quotation` draft — pricing-aware, **stateful** (attaches `QuotationLine` candidates to the quotation) | Body: `{quotation_id, date_from, date_to, adults, children, filters?}`. Response: `{lines: [QuotationLine, ...]}` (persisted; `is_selected=False` until the operator picks). The endpoint **creates/updates lines on the given quotation**, unlike `/availability:search` (no pricing, no state) and `/pricing:quote-bulk` (priced but stateless). See reconciliation issue #44. |

---

### 2.8 Bookings

The most action-heavy resource group. Lifecycle actions are POST verbs.

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/bookings` | List | filters: `status`, `property`, `guest`, `site`, `check_in_after/before`, `check_out_after/before`, `assigned_to`, `q`; `ordering=`; `include=property,guest,payments`. Default manager hides `is_archived=True` rows — use `/bookings/archived` for those. |
| POST | `/bookings` | Create | |
| GET | `/bookings/{id}` | Detail | |
| PATCH | `/bookings/{id}` | Update non-state fields | |
| _(no DELETE)_ | `/bookings/{id}` | Bookings are not deletable. Mistakes are corrected via `:cancel` with a reason, then `:archive` to tidy the row out of the default list; the underlying record always survives for audit. | |

#### State transitions (side-effecting)

State-machine semantics, allowed-from sets, and side effects are defined in `django_res_design/06-availability.md`. The API surface mirrors that machine; do not add actions here without a corresponding backend transition.

| Method | Path | Purpose |
|---|---|---|
| POST | `/bookings/{id}:confirm` | Alias for `:owner-approve` on bookings that require approval; otherwise advances `awaiting_deposit` workflows. |
| POST | `/bookings/{id}:cancel` | Cancel (with reason). Allowed from any non-terminal state; refund and hold-release handled by the service. |
| POST | `/bookings/{id}:owner-approve` | Owner-portal approval: `pending_owner_approval` → `awaiting_deposit`. |
| POST | `/bookings/{id}:owner-decline` | Owner-portal decline: `pending_owner_approval` → `declined`. |
| POST | `/bookings/{id}:modify-dates` | Date change. Acquires a fresh `BookingHold` on the new range, re-runs availability + change-over check, regenerates `pricing_snapshot`, and recomputes `balance_due` / `balance_due_at`. No status change. Refused from `checked_in` and from terminal states. |
| POST | `/bookings/{id}:modify-guests` | Party-size change. Re-runs the pricing engine because party size can resolve to a different rate rule (occupancy band). No status change. Refused from `checked_in` and from terminal states. |
| POST | `/bookings/{id}:archive` | Sets `is_archived = True` (and `archived_at`). Allowed only from terminal states (`checked_out`, `cancelled`, `expired`, `declined`). Orthogonal to `status`; **not** soft-delete. |
| POST | `/bookings/{id}:restore` | Sets `is_archived = False`. Returns booking to main list at its existing terminal status. |
| POST | `/bookings/{id}:check-in` | `balance_paid` → `checked_in`. |
| POST | `/bookings/{id}:check-out` | `checked_in` → `checked_out`. Manual operator action; the same backend method is invoked by a Celery beat task that auto-completes overdue stays. |
| POST | `/bookings/{id}:resend-confirmation` | Idempotent re-send of the latest confirmation email. No state change. |

#### Archive bookings (separate read surface)
| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/archived` | List archived bookings (separate index) |
| GET | `/bookings/archived/{id}` | Detail |

#### Notes & activity
| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/activity` | Timeline |
| GET | `/bookings/{id}/notes` | Notes |
| POST | `/bookings/{id}/notes` | Add note |
| PATCH / DELETE | `/bookings/{id}/notes/{note_id}` | Edit / remove |

#### Documents (contract, voucher)
| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/documents` | List generated docs |
| POST | `/bookings/{id}/documents:generate` | Generate (contract/voucher), async job |
| GET | `/bookings/{id}/documents/{doc_id}` | Fetch metadata + signed URL |

---

### 2.9 Concierge Line Items (sub-resource of booking)

| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/concierge-items` | List |
| POST | `/bookings/{id}/concierge-items` | Add |
| PATCH | `/bookings/{id}/concierge-items/{item_id}` | Update |
| DELETE | `/bookings/{id}/concierge-items/{item_id}` | Remove |
| POST | `/bookings/{id}/concierge-items:reorder` | Reorder |
| POST | `/bookings/{id}/concierge-items/{item_id}:confirm` | Mark confirmed |

---

### 2.10 Booking Payments — Deposit Track

Three parallel resource shapes (deposit, balance, security) — each is functionally the same surface but distinct paths so the UI can address each track independently.

| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/deposit` | Current deposit status + scheduled amount + due date |
| PATCH | `/bookings/{id}/deposit` | Update schedule / amount |
| GET | `/bookings/{id}/deposit/payments` | List payment attempts on this track |
| POST | `/bookings/{id}/deposit/payments` | Record a manual payment |
| GET | `/bookings/{id}/deposit/payments/{payment_id}` | Detail |
| POST | `/bookings/{id}/deposit/payments/{payment_id}:capture` | Capture authorized charge |
| POST | `/bookings/{id}/deposit/payments/{payment_id}:void` | Void uncaptured |
| POST | `/bookings/{id}/deposit:request-payment` | Email pay-link to guest |
| POST | `/bookings/{id}/deposit:mark-paid` | Manual override |
| POST | `/bookings/{id}/deposit:waive` | Waive |

---

### 2.11 Booking Payments — Balance Track

Mirrors deposit track exactly, replacing `deposit` with `balance` in every path.

| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/balance` | |
| PATCH | `/bookings/{id}/balance` | |
| GET / POST | `/bookings/{id}/balance/payments` | |
| GET | `/bookings/{id}/balance/payments/{payment_id}` | |
| POST | `/bookings/{id}/balance/payments/{payment_id}:capture` | |
| POST | `/bookings/{id}/balance/payments/{payment_id}:void` | |
| POST | `/bookings/{id}/balance:request-payment` | |
| POST | `/bookings/{id}/balance:mark-paid` | |
| POST | `/bookings/{id}/balance:waive` | |

---

### 2.12 Booking Payments — Security Deposit Track

| Method | Path | Purpose |
|---|---|---|
| GET | `/bookings/{id}/security` | |
| PATCH | `/bookings/{id}/security` | |
| GET / POST | `/bookings/{id}/security/payments` | |
| GET | `/bookings/{id}/security/payments/{payment_id}` | |
| POST | `/bookings/{id}/security/payments/{payment_id}:capture` | |
| POST | `/bookings/{id}/security/payments/{payment_id}:hold` | Pre-auth hold |
| POST | `/bookings/{id}/security/payments/{payment_id}:release` | Release hold |
| POST | `/bookings/{id}/security/payments/{payment_id}:claim` | Convert hold to charge (damage) |
| POST | `/bookings/{id}/security:request-payment` | |
| POST | `/bookings/{id}/security:mark-paid` | |

---

### 2.13 Refunds

| Method | Path | Purpose |
|---|---|---|
| GET | `/refunds` | List; filters: `booking`, `status`, `created_after/before` |
| POST | `/bookings/{id}/refunds` | Initiate refund against a booking (parent context) |
| GET | `/refunds/{id}` | Detail |
| POST | `/refunds/{id}:approve` | Approve pending |
| POST | `/refunds/{id}:reject` | Reject |
| POST | `/refunds/{id}:execute` | Push to gateway |
| POST | `/refunds/{id}:cancel` | Cancel before execution |

---

### 2.14 Payments (flat, cross-booking)

| Method | Path | Purpose |
|---|---|---|
| GET | `/payments` | Global list across tracks; filters `purpose` (`DEPOSIT`/`BALANCE`/`SECURITY_DEPOSIT`/`REFUND`/`ADJUSTMENT`), `gateway`, `status`, `currency`, date ranges |
| GET | `/payments/{id}` | Detail |

> Stored payment instruments (`/payment-methods`, `/guests/{id}/payment-methods`) are out of MVP scope; v1 captures cards per-transaction via the gateway's hosted fields, with no vaulted multi-method picker. The backend's `PaymentInstrument` model is retained as a one-row-per-charge audit record, not a reusable wallet. See reconciliation issue #13.

> The legacy `/checkouts` endpoint (which mirrored `VillaCheckoutDetail` — the 3-tier payment-schedule ledger of deposit / rental balance / security deposit rows) is **dropped**. Those rows are now `Payment(purpose ∈ {DEPOSIT, BALANCE, SECURITY_DEPOSIT})`; query via `GET /payments?purpose=…&booking=…` or the nested track endpoints under `/bookings/{id}/deposit`, `/balance`, `/security` (§2.12). See reconciliation issue #6.

---

### 2.15 Contacts (Owners, Agents, Managers, Accountants)

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/contacts` | List | filters: `role`, `site`, `country`, `q` |
| POST | `/contacts` | Create | |
| GET | `/contacts/{id}` | Detail | |
| PATCH | `/contacts/{id}` | Update | |
| DELETE | `/contacts/{id}` | Archive | |
| GET | `/contacts/{id}/emails` | List | |
| POST | `/contacts/{id}/emails` | Add | |
| PATCH / DELETE | `/contacts/{id}/emails/{email_id}` | | |
| POST | `/contacts/{id}/emails/{email_id}:set-primary` | | |
| GET | `/contacts/{id}/phones` | | |
| POST | `/contacts/{id}/phones` | | |
| PATCH / DELETE | `/contacts/{id}/phones/{phone_id}` | | |
| GET | `/contacts/{id}/properties` | Properties linked to this contact (reverse of property→contacts) | |
| POST | `/contacts/{id}:invite-portal` | Send owner-portal invite | |

---

### 2.16 Contact–Property Mapping (permissions & notifications)

The mapping is exposed both nested under property (see 2.2) and flat for permission-management UIs.

| Method | Path | Purpose |
|---|---|---|
| GET | `/contact-property-mappings` | Flat list; filters: `contact`, `property`, `role`, `notify_bookings` |
| GET | `/contact-property-mappings/{id}` | Detail |
| PATCH | `/contact-property-mappings/{id}` | Update flags |
| DELETE | `/contact-property-mappings/{id}` | Remove |

---

### 2.17 Guests / Clients

Distinct from `contacts`. These are the booking-side customers.

| Method | Path | Purpose |
|---|---|---|
| GET | `/guests` | List; filters: `country`, `site`, `q`, `created_after/before` |
| POST | `/guests` | Create |
| GET | `/guests/{id}` | Detail |
| PATCH | `/guests/{id}` | Update |
| DELETE | `/guests/{id}` | Archive (subject to GDPR rules — server may anonymize) |
| GET | `/guests/{id}/bookings` | Bookings for this guest |
| GET | `/guests/{id}/enquiries` | Enquiries for this guest |
| GET | `/guests/{id}/quotations` | |
| POST | `/guests/{id}:merge` | Merge duplicate guest records |
| POST | `/guests/{id}:anonymize` | GDPR erasure |

---

### 2.18 Users & Roles

| Method | Path | Purpose |
|---|---|---|
| GET | `/users` | List staff users; `?role=`, `?site=`, `?active=` |
| POST | `/users` | Create staff user |
| GET | `/users/{id}` | Detail |
| PATCH | `/users/{id}` | Update |
| DELETE | `/users/{id}` | Deactivate |
| POST | `/users/{id}:activate` | Reactivate |
| POST | `/users/{id}:reset-password` | Force reset (admin-initiated) |
| POST | `/users/{id}:reset-2fa` | Clear 2FA enrollment |
| GET | `/users/{id}/sessions` | Active sessions |
| DELETE | `/users/{id}/sessions/{session_id}` | Revoke |
| GET | `/roles` | Read-only enum listing of the fixed `StaffRole` values (`ADMIN`, `RESERVATIONS`, `ACCOUNTS`, `VIEWER`). For populating the `?role=` filter and the user-edit dropdown. No POST/PATCH/DELETE — roles are fixed in code. |

Roles in this rebuild are a fixed `User.role` enum, not editable. The legacy `VillaRoles` table was the *contact-property* role lookup (Owner/Agent/Villa Admin/Villa Manager/Management Co), surfaced via `/contact-property-mappings` and `/properties/{id}/contacts`, **not** a staff-role table. The legacy app had no editable staff-role concept — staff power was a single `UserMaster.IsSystemAdmin` flag. See reconciliation issue #9 and `09-departures.md` for the mapping.

For per-caller capability introspection use `GET /auth/permissions` (§2.0); fine-grained server-side permission checks ride on Django's built-in `auth.Permission` framework (per-model + the three custom `Property` permissions documented in `django_res_design/01-accounts.md`).

---

### 2.19 Email Templates & Email Logs

Transactional comms (booking confirmation, deposit request, owner-approval request, magic-link dispatch) are MVP — they're load-bearing for the booking workflow. The **template-editing admin is also MVP** per the `10-decisions.md` row "Editable `EmailTemplate` admin with versioning + preview-with-data + test-send" — this reverses the earlier v1.1-deferral. Templates ship as code seed data and are then operator-editable through this surface; the `comms` model carries versioning natively (`10-comms.md`). The log surface is forensic-essential and is exposed both globally and as a per-booking sub-resource for the Communications tab (`product-design/02-frontend-design.md §3.8`). See also reconciliation issue #10.

#### Templates
| Method | Path | Purpose |
|---|---|---|
| GET | `/email-templates` | List active templates; filter `key`, `is_active` |
| GET | `/email-templates/{key}` | Detail by key (resolves the active version) |
| PUT | `/email-templates/{key}` | Publish a new version of this key — atomically deactivates the prior active row and inserts a new one with `version = prior + 1`. Body: `{subject_template, body_template, notes?}` |
| POST | `/email-templates/{key}:preview` | Render with sample or real data. Body: `{context?: dict, booking_id?, quotation_id?, enquiry_id?}` (one of the FK ids resolves to a real context; bare `context` is for synthetic data). Response: `{rendered_subject, rendered_body_html, rendered_body_text}` |
| POST | `/email-templates/{key}:test-send` | Render and dispatch through the active `SmtpProfile` to a chosen recipient. Body: `{to, context_source: same shape as :preview}`. Writes an `EmailLog` row with `correlation.test_send=True` |
| GET | `/email-templates/{key}/versions` | Version history (newest first) |
| GET | `/email-templates/{key}/versions/{n}` | Specific historical version (read-only) |

#### Logs
| Method | Path | Purpose |
|---|---|---|
| GET | `/email-logs` | Global list; filters: `booking`, `enquiry`, `guest`, `quotation`, `template_key`, `status`, date ranges |
| GET | `/email-logs/{id}` | Detail incl. rendered body |
| GET | `/bookings/{id}/email-logs` | Per-booking communications history (Comms tab on Booking Detail, `02-frontend-design.md §3.8`). Returns `EmailLog` rows where `correlation.booking_id = {id}`, newest first. Filters: `template_key`, `status` |
| POST | `/bookings/{id}/email-logs/{log_id}:resend` | Re-dispatch a previously sent email — re-renders against the current booking state and writes a NEW `EmailLog` row (the original is not mutated; append-only per `10-comms.md`) |
| POST | `/bookings/{id}/compose-email` | Operator-composed one-off email against this booking. Body: `{template_key, to, cc?, bcc?, context_overrides?}` — template provides defaults; context is the booking's resolved context plus operator overrides. Renders preview server-side; an explicit `confirm: true` flag dispatches |
| GET | `/code-auth-logs` | Magic-link/code dispatch log (separate from `EmailLog` — narrower fields) |

> Bulk-resend (`POST /email-logs/bulk-resend`) remains deferred to v1.1 — the per-booking and single-row resends above cover the operator-UX cases the legacy gap analysis surfaced.

---

### 2.20 Reports

All reports support `?from=&to=&site=&currency=` at minimum; specifics noted inline. Reports return JSON; same data is exportable via the export endpoint group (2.21).

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/reports/occupancy` | Occupancy by villa/region/period | `?group_by=property\|region\|month` |
| GET | `/reports/revenue` | Gross / net revenue | `?group_by=property\|month\|site` |
| GET | `/reports/owner-statements` | Per-owner statement | `?contact=&period=` |
| GET | `/reports/owner-statements/{contact_id}` | Single owner detail | |
| GET | `/reports/commissions` | Commission breakdown | |
| GET | `/reports/tax` | Tax collected | |
| GET | `/reports/payments` | Payment flow report | |
| GET | `/reports/refunds` | Refund summary | |
| GET | `/reports/enquiry-funnel` | Lead → quote → booking conversion | |

---

### 2.21 Exports (async job pattern)

| Method | Path | Purpose |
|---|---|---|
| POST | `/exports` | Create export job; body specifies report type + filters + format (csv/pdf/xlsx) |
| GET | `/exports` | List own export jobs |
| GET | `/exports/{id}` | Status + download URL when ready |
| DELETE | `/exports/{id}` | Cancel / delete |

Generic async-job surface (used by exports, doc generation, bulk ops):

| Method | Path | Purpose |
|---|---|---|
| GET | `/jobs/{id}` | Poll job status |
| POST | `/jobs/{id}:cancel` | Cancel |

---

### 2.22 Bulk Operations

Convention: `POST /{resource}/bulk` for create/update, `POST /{resource}/bulk-delete` for deletes. Notable bulk endpoints:

| Method | Path | Purpose |
|---|---|---|
| POST | `/properties/bulk` | Bulk create/update |
| POST | `/properties/bulk-delete` | |
| POST | `/properties/bulk:tag` | Apply feature/collection to many |
| POST | `/availability/bulk-block` | (also listed in 2.5) |
| POST | `/rate-cards/bulk` | Mass-create rate cards across seasons |
| POST | `/contacts/bulk-import` | CSV import (async) |
| POST | `/guests/bulk-import` | CSV import (async) |

---

### 2.23 Search (global / command-palette)

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/search` | Global cross-entity search | `?q=`, `?types=properties,bookings,contacts,guests,enquiries`, `?limit=` |
| GET | `/search/suggest` | Autocomplete suggestions | type-ahead |
| GET | `/search/recent` | Caller's recent searches | |

---

### 2.24 iCal Feeds — deferred to v1.1

iCal export of availability/bookings is **not part of MVP**. No backend model is specified for signed feed tokens, and there is no day-1 ops requirement for OTA-style calendar subscription. Revisit when OTA channel integration (issue #11) is scoped. See reconciliation issue #12.

(Endpoints removed from v1: `GET /feeds/properties/{id}/ical`, `GET /feeds/contacts/{id}/ical`, `POST /properties/{id}/feeds/ical:rotate-token`, `GET /properties/{id}/feeds/ical`.)

---

### 2.25 Channel Sync — out of MVP scope

OTA channel-manager integration (Airbnb / Booking.com / VRBO inbound webhooks and outbound availability/rate push) is **future scope** and not part of v1. There is no backend channel-sync service, no `ChannelSyncJob` workflow wired beyond the model stub, and no day-1 ops dependency on OTA presence. Revisit as a discrete project. See reconciliation issue #11.

(Endpoints removed from v1: `POST /webhooks/airbnb`, `POST /webhooks/booking`, `POST /webhooks/vrbo`, `GET /channel-sync/inbound-log`, `GET /channel-sync/status`, `POST /channel-sync:sync-property`, `POST /channel-sync:sync-all`, `GET /channel-sync/jobs`, `GET /channel-sync/jobs/{id}`.)

---

### 2.26 Zoho CRM Sync

| Method | Path | Purpose |
|---|---|---|
| GET | `/zoho/status` | Connection + last-sync timestamp |
| POST | `/zoho:connect` | Begin OAuth |
| POST | `/zoho:disconnect` | Revoke |
| POST | `/zoho:sync-contacts` | Trigger contact sync |
| POST | `/zoho:sync-properties` | Trigger property sync |
| POST | `/zoho:sync-enquiries` | Trigger enquiry sync |
| GET | `/zoho/sync-log` | Sync job history |
| GET | `/zoho/sync-log/{id}` | Job detail |
| POST | `/zoho/sync-log/{id}:retry` | Retry failed |

---

### 2.27 Payment Gateway Webhooks

| Method | Path | Purpose | Notes |
|---|---|---|---|
| POST | `/webhooks/flywire` | Flywire payment-status webhook | HMAC verified on raw body |
| POST | `/webhooks/{gateway}` | Generic per-gateway slot (reserved for a future second provider) | not wired in v1 |
| GET | `/webhooks/log` | Audit log of inbound webhook attempts | admin |
| POST | `/webhooks/log/{id}:replay` | Replay a stored webhook | admin |

---

### 2.28 System Config / Settings

| Method | Path | Purpose |
|---|---|---|
| GET | `/system/settings` | Global config (read of `SystemDefaults`) |
| PATCH | `/system/settings` | Update |
| GET | `/system/integrations` | Integration list + last-sync health for the configured providers (Zoho, WordPress fan-out, payment gateway). Admin-only. |
| GET | `/system/integrations/{key}` | Detail (credentials surfaced redacted) |
| POST | `/system/integrations/{key}:test` | Connectivity test (e.g., Zoho ping, WP API auth, Flywire key validity) |

> Backed by per-provider configuration carried on `SystemDefaults` keys plus the existing `ZohoSyncJob` / sync-record state. No new top-level `Integration` model is required for MVP; if config-row identity becomes important post-v1, promote `key` to a dedicated table. See reconciliation issue #21.

---

### 2.29 Terms & Conditions Versions

Append-only legal-copy versioning. `reservations.TermsVersion` rows are snapshotted by `Quotation.terms_version` and `Booking.terms_version` at creation, so older versions stay queryable for audit and dispute resolution. There is no `PATCH` or `DELETE` — correcting a published version means publishing a new one. See reconciliation issue #33.

| Method | Path | Purpose |
|---|---|---|
| GET | `/terms-versions` | List all versions (newest first); admin |
| POST | `/terms-versions` | Create a new draft version (body: `{version, body_markdown}`); not yet `is_current` |
| GET | `/terms-versions/current` | Resolver — returns the single row where `is_current=True`. Public-readable for quotation acceptance |
| GET | `/terms-versions/{version}` | Detail by version slug (e.g. `2026-01`) |
| POST | `/terms-versions/{version}:publish` | Atomically flip `is_current=True` on this row, `False` on the prior current row, set `published_at=now()` (idempotent — re-publishing the current row is a no-op) |

---

## 3. State-Transition Action Inventory

Consolidated list of named side-effecting actions, grouped by parent resource. All are `POST /{resource}/{id}:{action}`.

**Properties:** `activate`, `archive`, `duplicate`, `restore`, `import-from-zoho`. (`activate` / `archive` drive `Property.status ∈ {draft, active, archived}` — see reconciliation issue #23. The prior `:publish` / `:unpublish` verbs are dropped.) Image sub-action: `reorder`, `set-hero`.

**Enquiries:** `assign`, `convert`, `close`, `reopen`.

**Quotations:** `send`, `duplicate`, `convert`, `withdraw`. Lines: `reorder`.

**Bookings:** `confirm`, `cancel`, `owner-approve`, `owner-decline`, `modify-dates`, `modify-guests`, `archive`, `restore`, `check-in`, `check-out`, `resend-confirmation`. Documents: `generate`.

**Concierge items:** `confirm`, `reorder`.

**Deposit / Balance / Security tracks:** `request-payment`, `mark-paid`, `waive` (deposit/balance), and on the individual payment: `capture`, `void`. Security adds `hold`, `release`, `claim`.

**Refunds:** `approve`, `reject`, `execute`, `cancel`.

**Availability:** `extend-hold`, `release-hold`, `bulk-block`.

**Email templates / logs:** `preview`, `test-send` (on `/email-templates/{key}`); `resend` (on `/bookings/{id}/email-logs/{log_id}`); plus a per-booking compose surface (`POST /bookings/{id}/compose-email`). Bulk-resend remains v1.1. See §2.19 and reconciliation issue #10.

**Channel sync:** _(out of MVP scope — see §2.25 and reconciliation issue #11.)_

**Zoho:** `connect`, `disconnect`, `sync-contacts`, `sync-properties`, `sync-enquiries`. Jobs: `retry`.

**Webhooks:** `replay` (admin replay of stored inbound).

**Users:** `activate`, `reset-password`, `reset-2fa`.

**Discounts:** `lookup-code` (POST /discounts:lookup-code — validate a promo code; rate-limited; see §2.4 and reconciliation issue #32).

**Terms versions:** `publish` (POST /terms-versions/{version}:publish — atomic flip of `is_current`; see §2.29 and reconciliation issue #33).

**Contacts:** `invite-portal`. Emails: `set-primary`.

**Guests:** `merge`, `anonymize`.

**Auth:** `request`, `confirm` (password reset); `challenge`, `verify`, `enroll`, `disable` (2FA); `request`, `consume` (magic link).

**Pricing helpers:** `quote`, `quote-bulk` (stateless calc — listed here for completeness; not state-mutating but follows the verb form).

**Jobs:** `cancel`.

**Exports / Documents:** `generate` (documents), implicit job creation (exports).

---

## 4. Cross-Cutting Endpoints

### Health & ops
| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/health` | Liveness | anon |
| GET | `/health/ready` | Readiness (DB, cache, gateway connectivity) | anon |
| GET | `/system/version` | Build version, git sha | anon |
| GET | `/system/time` | Server clock (for client skew detection) | anon |

### Audit log
| Method | Path | Purpose |
|---|---|---|
| GET | `/audit-log` | Query log; filters: `actor`, `entity_type`, `entity_id`, `action`, date range |
| GET | `/audit-log/{id}` | Detail |
| GET | `/{resource}/{id}/audit-log` | Scoped audit log per entity (alias) |

### Notifications (in-app)
| Method | Path | Purpose |
|---|---|---|
| GET | `/notifications` | List own notifications; `?unread=true` |
| GET | `/notifications/{id}` | Detail |
| POST | `/notifications/{id}:mark-read` | |
| POST | `/notifications:mark-all-read` | |
| DELETE | `/notifications/{id}` | Dismiss |
| GET | `/notification-preferences` | Channel + topic prefs |
| PATCH | `/notification-preferences` | Update |

### Feature flags
Backed by the `FeatureFlag` entity (see `01-domain-model.md` §11). Minimal surface — internal infra, not customer-facing.

| Method | Path | Purpose |
|---|---|---|
| GET | `/feature-flags` | Caller's effective flags (resolves `is_enabled_default`, per-user override, rollout cohort). Admin can pass `?all=true` to see the full catalogue. |
| PATCH | `/feature-flags/{key}` | Update flag definition (admin only) |

### Uploads
| Method | Path | Purpose |
|---|---|---|
| POST | `/uploads:sign` | Get presigned PUT URL |
| POST | `/uploads` | Direct multipart upload (small files) |
| GET | `/uploads/{key}` | Metadata lookup |

### Public / unauthenticated mirror
The marketing-site read surface lives under `/api/v1/public/` and exposes a curated subset:
- `GET /public/properties`, `GET /public/properties/{slug}`
- `GET /public/regions`, `GET /public/regions/{slug}/properties`
- `GET /public/collections`, `GET /public/collections/{slug}/properties`
- `GET /public/features`
- `POST /public/enquiries`
- `POST /public/availability:search`, `POST /public/pricing:quote`
